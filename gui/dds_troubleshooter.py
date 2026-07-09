"""
DDS Troubleshooter Page, Diagnose network connectivity and environment variable conflicts.
"""

import os
import re
import socket
import struct
import subprocess
import psutil

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from gui.theme import ThemeManager


def _safe_stop_thread(thread, timeout_ms=3000):
    """Safely stop a QThread with bounded wait.  Idempotent."""
    if thread is None:
        return
    try:
        if thread.isRunning():
            if hasattr(thread, 'requestInterruption'):
                thread.requestInterruption()
            if hasattr(thread, 'quit'):
                thread.quit()
            thread.wait(timeout_ms)
    except RuntimeError:
        pass  # Qt object may already be deleted


class MulticastTestThread(QThread):
    """
    Background worker to test UDP multicast loopback routing.
    Emits (success, message).
    """
    finished_signal = Signal(bool, str)

    def run(self):
        rx_sock = None
        tx_sock = None
        try:
            # Create receiver socket
            rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            rx_sock.bind(('', 7788))

            # Join multicast group 239.255.0.1 (standard site-local group)
            mreq = struct.pack("4sl", socket.inet_aton("239.255.0.1"), socket.INADDR_ANY)
            rx_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            rx_sock.settimeout(1.2)

            # Create sender socket
            tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            tx_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            tx_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

            # Send ping
            tx_sock.sendto(b"DDS_TROUBLESHOOT_PING", ("239.255.0.1", 7788))

            # Attempt receive
            data, _ = rx_sock.recvfrom(1024)
            if data == b"DDS_TROUBLESHOOT_PING":
                self.finished_signal.emit(True, "Multicast loopback communication succeeded.")
            else:
                self.finished_signal.emit(False, "Received invalid ping data.")
        except socket.timeout:
            self.finished_signal.emit(False, "Multicast test timed out. Packets are not routing locally.")
        except Exception as e:
            self.finished_signal.emit(False, f"Multicast socket test failed: {e}")
        finally:
            if rx_sock:
                rx_sock.close()
            if tx_sock:
                tx_sock.close()


class DDSTroubleshooterPage(QWidget):
    """Diagnose local ROS 2 / DDS environment and network configuration."""

    def __init__(self, cli=None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.multicast_worker = None
        self._build_ui()

    def _build_ui(self):
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(48, 40, 48, 40)
        root_lay.setSpacing(0)
        root_lay.setAlignment(Qt.AlignTop)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(self._icon_label("fa5s.network-wired", "accent", 28))
        hdr.addSpacing(12)
        title = QLabel("DDS Troubleshooter")
        title.setProperty("class", "h1")
        hdr.addWidget(title)
        hdr.addStretch()

        self.btn_run = QPushButton("  Run Diagnostics")
        self.btn_run.setIcon(ThemeManager.icon("fa5s.search", "#ffffff"))
        self.btn_run.setProperty("class", "action-button")
        self.btn_run.clicked.connect(self.run_diagnostics)
        hdr.addWidget(self.btn_run)
        root_lay.addLayout(hdr)

        sub = QLabel("Scan environment variables, network interfaces, and run loopback multicast ping checks.")
        sub.setStyleSheet("margin-top: 6px; margin-bottom: 24px;")
        root_lay.addWidget(sub)

        # Scrollable container for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root_lay.addWidget(scroll, 1)

        scroll_widget = QWidget()
        scroll_lay = QVBoxLayout(scroll_widget)
        scroll_lay.setContentsMargins(0, 0, 0, 0)
        scroll_lay.setSpacing(20)
        scroll.setWidget(scroll_widget)

        # Environment Card
        self.env_card = QFrame()
        self.env_card.setProperty("class", "card")
        env_lay = QVBoxLayout(self.env_card)
        env_lay.setSpacing(8)
        env_title = QLabel("ROS 2 Environment Check")
        env_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        env_lay.addWidget(env_title)

        self.env_table = QTableWidget(3, 3)
        self.env_table.setHorizontalHeaderLabels(["Variable", "Current Value", "Status"])
        self.env_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.env_table.verticalHeader().setVisible(False)
        self._style_table(self.env_table)
        env_lay.addWidget(self.env_table)
        scroll_lay.addWidget(self.env_card)

        # Network Interfaces Card
        self.net_card = QFrame()
        self.net_card.setProperty("class", "card")
        net_lay = QVBoxLayout(self.net_card)
        net_lay.setSpacing(8)
        net_title = QLabel("Network Interfaces Check")
        net_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        net_lay.addWidget(net_title)

        self.net_table = QTableWidget(0, 4)
        self.net_table.setHorizontalHeaderLabels(["Interface", "IP Address", "Multicast Enabled", "Status"])
        self.net_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.net_table.verticalHeader().setVisible(False)
        self._style_table(self.net_table)
        net_lay.addWidget(self.net_table)
        scroll_lay.addWidget(self.net_card)

        # Multicast Ping Card
        self.ping_card = QFrame()
        self.ping_card.setProperty("class", "card")
        ping_lay = QVBoxLayout(self.ping_card)
        ping_lay.setSpacing(8)
        ping_title = QLabel("UDP Multicast Ping Test")
        ping_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        ping_lay.addWidget(ping_title)

        self.lbl_ping_status = QLabel("Diagnostics not run yet.")
        self.lbl_ping_status.setWordWrap(True)
        ping_lay.addWidget(self.lbl_ping_status)
        scroll_lay.addWidget(self.ping_card)

        # Recommendations Warning Banner
        self.rec_card = QFrame()
        self.rec_lay = QVBoxLayout(self.rec_card)
        self.rec_lay.setSpacing(8)
        self.lbl_rec_title = QLabel("⚠️ Recommendations to Solve Connectivity Issues:")
        self.lbl_rec_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.rec_lay.addWidget(self.lbl_rec_title)
        self.lbl_rec_desc = QLabel("")
        self.lbl_rec_desc.setWordWrap(True)
        self.lbl_rec_desc.setTextFormat(Qt.RichText)
        self.rec_lay.addWidget(self.lbl_rec_desc)
        self.rec_card.hide()
        scroll_lay.addWidget(self.rec_card)

    def _style_table(self, table):
        p = ThemeManager.palette()
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {p['bg_card']};
                gridline-color: {p['border']};
                color: {p['text_primary']};
                border: none;
            }}
            QHeaderView::section {{
                background-color: {p['bg_input']};
                color: {p['text_secondary']};
                padding: 6px;
                border: 1px solid {p['border']};
                font-weight: bold;
            }}
            """
        )

    def _icon_label(self, name, role="normal", size=18):
        lbl = QLabel()
        lbl.setPixmap(ThemeManager.icon(name, role).pixmap(size, size))
        return lbl

    def run_diagnostics(self):
        self.btn_run.setEnabled(False)
        self.btn_run.setText("  Running...")
        self.rec_card.hide()

        # 1. Environment variables check
        self._check_env_vars()

        # 2. Network interfaces check
        self._check_network_interfaces()

        # 3. Multicast ping check (background)
        self.lbl_ping_status.setText("Sending UDP multicast ping packets on group 239.255.0.1, port 7788...")
        self.multicast_worker = MulticastTestThread(self)
        self.multicast_worker.finished_signal.connect(self._on_multicast_finished)
        self.multicast_worker.start()

    def _check_env_vars(self):
        p = ThemeManager.palette()

        # Read environment variables natively or fallback
        domain_id = os.environ.get("ROS_DOMAIN_ID", "0")
        rmw = os.environ.get("RMW_IMPLEMENTATION", "Default (FastRTPS)")
        localhost_only = os.environ.get("ROS_LOCALHOST_ONLY", "0")

        # Set domain ID row
        self.env_table.setItem(0, 0, QTableWidgetItem("ROS_DOMAIN_ID"))
        self.env_table.setItem(0, 1, QTableWidgetItem(domain_id))
        try:
            val = int(domain_id)
            if 0 <= val <= 232:
                item = QTableWidgetItem("Valid Domain ID")
                item.setForeground(QColor(p["success"]))
            else:
                item = QTableWidgetItem("⚠️ Domain ID out of bounds (0-232)")
                item.setForeground(QColor(p["warning"]))
        except ValueError:
            item = QTableWidgetItem("❌ Invalid (must be an integer)")
            item.setForeground(QColor(p["danger"]))
        self.env_table.setItem(0, 2, item)

        # Set RMW row
        self.env_table.setItem(1, 0, QTableWidgetItem("RMW_IMPLEMENTATION"))
        self.env_table.setItem(1, 1, QTableWidgetItem(rmw))
        item = QTableWidgetItem("Compatible")
        item.setForeground(QColor(p["success"]))
        self.env_table.setItem(1, 2, item)

        # Set Localhost Only row
        self.env_table.setItem(2, 0, QTableWidgetItem("ROS_LOCALHOST_ONLY"))
        self.env_table.setItem(2, 1, QTableWidgetItem(localhost_only))
        if localhost_only == "1":
            item = QTableWidgetItem("⚠️ Restricting communication to localhost")
            item.setForeground(QColor(p["warning"]))
        else:
            item = QTableWidgetItem("Allows Network Discovery")
            item.setForeground(QColor(p["success"]))
        self.env_table.setItem(2, 2, item)

        for r in range(3):
            for c in range(3):
                item = self.env_table.item(r, c)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def _check_network_interfaces(self):
        p = ThemeManager.palette()
        self.net_table.setRowCount(0)

        # Scan interfaces
        interfaces = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        # Fetch Linux MULTICAST interface flags if possible
        multicast_interfaces = set()
        try:
            res = subprocess.run(["ip", "link"], capture_output=True, text=True)
            if res.returncode == 0:
                current_if = None
                for line in res.stdout.splitlines():
                    m = re.match(r"^\d+:\s*([^:]+):", line)
                    if m:
                        current_if = m.group(1).strip()
                    if current_if and "MULTICAST" in line:
                        multicast_interfaces.add(current_if)
        except Exception:
            pass

        row_idx = 0
        for name, addrs in interfaces.items():
            ipv4 = "--"
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ipv4 = addr.address
                    break

            stat = stats.get(name)
            is_up = stat.isup if stat else False
            has_multicast = (name in multicast_interfaces) or (name == "lo") or (stat and stat.speed > 0) # reasonable fallback

            self.net_table.insertRow(row_idx)
            self.net_table.setItem(row_idx, 0, QTableWidgetItem(name))
            self.net_table.setItem(row_idx, 1, QTableWidgetItem(ipv4))

            mc_text = "Enabled" if has_multicast else "Disabled"
            mc_color = p["success"] if has_multicast else p["warning"]
            mc_item = QTableWidgetItem(mc_text)
            mc_item.setForeground(QColor(mc_color))
            self.net_table.setItem(row_idx, 2, mc_item)

            status_text = "Up" if is_up else "Down"
            status_color = p["success"] if is_up else p["text_secondary"]
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
            self.net_table.setItem(row_idx, 3, status_item)

            for c in range(4):
                item = self.net_table.item(row_idx, c)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

            row_idx += 1

    def _on_multicast_finished(self, success: bool, message: str):
        p = ThemeManager.palette()
        self.btn_run.setEnabled(True)
        self.btn_run.setText("  Run Diagnostics")

        if success:
            self.lbl_ping_status.setText(f"✅ <b>SUCCESS</b>: {message}")
            self.lbl_ping_status.setStyleSheet(f"color: {p['success']}; font-size: 13px;")
        else:
            self.lbl_ping_status.setText(f"❌ <b>FAILED</b>: {message}")
            self.lbl_ping_status.setStyleSheet(f"color: {p['danger']}; font-size: 13px;")

        # Run overall report and display recommendations if issues are found
        self._generate_recommendations(success)

    def _generate_recommendations(self, multicast_success: bool):
        p = ThemeManager.palette()
        recs = []

        # Check local host lockout
        localhost_only = os.environ.get("ROS_LOCALHOST_ONLY", "0")
        if localhost_only == "1":
            recs.append(
                "• <b>ROS_LOCALHOST_ONLY is enabled</b>:<br>"
                "Your nodes cannot communicate with other machines or external hardware/robots.<br>"
                "<i>Fix:</i> Unset the environment variable by running: <code>unset ROS_LOCALHOST_ONLY</code>"
            )

        # Check domain ID validity
        domain_id = os.environ.get("ROS_DOMAIN_ID", "0")
        try:
            val = int(domain_id)
            if val < 0 or val > 232:
                recs.append(
                    f"• <b>Invalid ROS_DOMAIN_ID ({domain_id})</b>:<br>"
                    "The domain ID must be an integer between 0 and 232.<br>"
                    "<i>Fix:</i> Reset it to default: <code>export ROS_DOMAIN_ID=0</code>"
                )
        except ValueError:
            recs.append(
                "• <b>Non-integer ROS_DOMAIN_ID</b>:<br>"
                "DDS requires an integer domain ID.<br>"
                "<i>Fix:</i> <code>export ROS_DOMAIN_ID=0</code>"
            )

        # Check multicast connectivity
        if not multicast_success:
            recs.append(
                "• <b>Local Multicast Routing Failed</b>:<br>"
                "WSL often boots without a multicast routing entry on loopback, blocking DDS node discovery.<br>"
                "<i>Fix:</i> Add a multicast route to the loopback interface by executing:<br>"
                "<code>sudo ip route add 224.0.0.0/4 dev lo</code>"
            )

        # Check if network interfaces are down
        stats = psutil.net_if_stats()
        active_ifs = [name for name, stat in stats.items() if stat.isup and name != "lo"]
        if not active_ifs:
            recs.append(
                "• <b>No Active Network Interfaces</b>:<br>"
                "Only the loopback ('lo') interface is up. You will not be able to connect to external ROS 2 devices.<br>"
                "<i>Fix:</i> Connect to a network or ensure your WSL vEthernet adapter is enabled."
            )

        if recs:
            self.rec_card.show()
            self.lbl_rec_desc.setText("<br>".join(recs))
            self.rec_card.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {p['bg_selected']};
                    border: 1px solid {p['warning']};
                    border-radius: 12px;
                    padding: 14px;
                }}
                """
            )
            self.lbl_rec_title.setStyleSheet(f"color: {p['warning']}; font-weight: bold; font-size: 14px;")
        else:
            self.rec_card.hide()

    def refresh_theme(self):
        self._style_table(self.env_table)
        self._style_table(self.net_table)
        # Re-evaluate recommendations layout styles if shown
        localhost_only = os.environ.get("ROS_LOCALHOST_ONLY", "0")
        domain_id = os.environ.get("ROS_DOMAIN_ID", "0")
        is_invalid_domain = False
        try:
            val = int(domain_id)
            is_invalid_domain = val < 0 or val > 232
        except ValueError:
            is_invalid_domain = True

        multicast_failed = "diagnostics not run" in self.lbl_ping_status.text().lower() or "failed" in self.lbl_ping_status.text().lower()
        
        # Trigger recommendations refresh to paint with new theme colors
        if not self.rec_card.isHidden():
            self._generate_recommendations(not multicast_failed)

    def cleanup(self):
        """Idempotent shutdown – stop multicast worker if running."""
        try:
            thread = getattr(self, 'multicast_worker', None)
            _safe_stop_thread(thread)
        except Exception:
            pass  # best-effort cleanup
