import subprocess
import shlex
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QGraphicsView, QGraphicsScene, QLabel
from PySide6.QtCore import Qt, QRectF, QThread, Signal
from PySide6.QtGui import QBrush, QPen, QColor
from core.ros2_cli import ROS2CLI

class TopologyWorker(QThread):
    finished_signal = Signal(dict)

    def __init__(self, cli):
        super().__init__()
        self.cli = cli

    def run(self):
        try:
            topology = self.cli.get_topology()
            self.finished_signal.emit(topology)
        except Exception:
            self.finished_signal.emit({"nodes": [], "topics": [], "edges": []})


class VisualizerPage(QWidget):
    def __init__(self, cli: ROS2CLI, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.worker = None
        self.last_plain_output = None
        
        layout = QVBoxLayout(self)
        
        self.refresh_btn = QPushButton("Refresh Topology")
        self.refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_btn)

        self.info_label = QLabel("Note: The visualizer only displays Active/Running nodes. If your workspace nodes are not launched, they will not appear here.")
        self.info_label.setStyleSheet("font-style: italic;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        layout.addWidget(self.view)
        
    def refresh(self):
        if self.worker and self.worker.isRunning():
            return  # Already loading
            
        self.refresh_btn.setText("Loading Topology...")
        self.refresh_btn.setEnabled(False)
        self.scene.clear()
        
        # Show loading text
        loading_text = self.scene.addText("Querying ROS 2 topology graph in background...")
        loading_text.setDefaultTextColor(QColor("#8892a4"))
        
        self.worker = TopologyWorker(self.cli)
        self.worker.finished_signal.connect(self._on_topology_loaded)
        self.worker.start()
        
    def _on_topology_loaded(self, topology: dict):
        self.refresh_btn.setText("Refresh Topology")
        self.refresh_btn.setEnabled(True)
        self.scene.clear()
        
        if not topology['nodes'] and not topology['topics']:
            no_data_text = self.scene.addText("No active nodes or topics found in the network.")
            no_data_text.setDefaultTextColor(QColor("#8892a4"))
            return
            
        dot_str = "digraph G {\n"
        dot_str += '  node [shape=box];\n'
        for n in topology['nodes']:
            dot_str += f'  "{n}" [shape=box];\n'
        
        for t in topology['topics']:
            dot_str += f'  "{t}" [shape=ellipse];\n'
            
        for edge in topology['edges']:
            src = edge['src']
            dst = edge['dst']
            dot_str += f'  "{src}" -> "{dst}";\n'
            
        dot_str += "}\n"
        
        try:
            # Note: Requires graphviz `dot` executable in system PATH
            process = subprocess.run(
                ['dot', '-Tplain'],
                input=dot_str,
                capture_output=True,
                text=True,
                check=True
            )
            self.last_plain_output = process.stdout
            self.parse_and_draw(process.stdout)
        except Exception as e:
            print(f"Error running dot: {e}")
            err_text = self.scene.addText(f"Error rendering Graphviz topology:\n{e}\n\nEnsure 'dot' (Graphviz) is installed.")
            err_text.setDefaultTextColor(QColor("#ef4444"))
            
    def parse_and_draw(self, plain_output: str):
        from gui.theme import ThemeManager
        p = ThemeManager.palette()
        border_color = QColor(p["border"])
        accent_color = QColor(p["accent"])
        success_color = QColor(p["success"])
        node_text_color = QColor("#ffffff")
        line_color = QColor(p["text_primary"])

        scale_factor = 72.0
        
        graph_height = 0
        lines = plain_output.strip().split('\n')
        for line in lines:
            parts = line.split()
            if not parts: continue
            if parts[0] == 'graph':
                graph_height = float(parts[3])
                break
                
        for line in lines:
            if not line: continue
            parts = shlex.split(line)
            if parts[0] == 'node':
                name = parts[1]
                x = float(parts[2]) * scale_factor
                y = (graph_height - float(parts[3])) * scale_factor
                w = float(parts[4]) * scale_factor
                h = float(parts[5]) * scale_factor
                shape = parts[8]
                
                rect = QRectF(x - w/2, y - h/2, w, h)
                if shape == 'box':
                    self.scene.addRect(rect, QPen(border_color), QBrush(accent_color))
                    text = self.scene.addText(name)
                    text.setDefaultTextColor(node_text_color)
                    br = text.boundingRect()
                    text.setPos(x - br.width()/2, y - br.height()/2)
                else:
                    self.scene.addEllipse(rect, QPen(border_color), QBrush(success_color))
                    text = self.scene.addText(name)
                    text.setDefaultTextColor(node_text_color)
                    br = text.boundingRect()
                    text.setPos(x - br.width()/2, y - br.height()/2)
                    
            elif parts[0] == 'edge':
                n_pts = int(parts[3])
                pts_list = parts[4:4+n_pts*2]
                for i in range(n_pts - 1):
                    x1 = float(pts_list[i*2]) * scale_factor
                    y1 = (graph_height - float(pts_list[i*2+1])) * scale_factor
                    x2 = float(pts_list[(i+1)*2]) * scale_factor
                    y2 = (graph_height - float(pts_list[(i+1)*2+1])) * scale_factor
                    self.scene.addLine(x1, y1, x2, y2, QPen(line_color, 1.5))
                    
    def refresh_theme(self):
        if self.last_plain_output:
            self.scene.clear()
            self.parse_and_draw(self.last_plain_output)
