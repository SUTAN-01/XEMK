import sys
import json
import asyncio
import websockets
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from typing import List, Dict, Any, Optional
import threading
import time
from datetime import datetime
from collections import defaultdict

# ======================= 数据模型类 =======================
class Card:
    """卡牌数据模型"""
    def __init__(self, data: Dict[str, Any]):
        self.name = data.get('name', '')
        self.HP = data.get('HP', 0)
        self.ATK = data.get('ATK', 0)
        self.property = data.get('property', '')
        self.race = data.get('race', '')
        self.cost = data.get('cost', [])
        self.card_id = data.get('id', data.get('card_id', ''))
        self.unique_id = f"{self.name}_{hash(str(data))}"

class CardUsage:
    """卡牌使用状态"""
    def __init__(self, card: Card):
        self.card = card
        self.used = False
        self.slot_index = -1

# ======================= 自定义控件 =======================
class CardWidget(QWidget):
    """卡牌显示控件"""
    def __init__(self, card: Card, parent=None):
        super().__init__(parent)
        self.card = card
        self.is_used = False
        self.is_dragging = False
        
        self.setFixedSize(180, 240)
        self.setCursor(Qt.PointingHandCursor)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制卡牌背景
        if self.is_used:
            painter.fillRect(self.rect(), QColor(245, 245, 245))
            border_color = QColor(108, 117, 125)
            header_gradient = QLinearGradient(0, 0, 0, 40)
            header_gradient.setColorAt(0, QColor(108, 117, 125))
            header_gradient.setColorAt(1, QColor(73, 80, 87))
        else:
            painter.fillRect(self.rect(), Qt.white)
            border_color = QColor(0, 123, 255)
            header_gradient = QLinearGradient(0, 0, 0, 40)
            header_gradient.setColorAt(0, QColor(0, 123, 255))
            header_gradient.setColorAt(1, QColor(0, 86, 179))
        
        # 绘制边框
        if self.is_dragging:
            border_color = border_color.darker(120)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(1, 1, self.width()-2, self.height()-2, 8, 8)
        
        # 绘制卡牌头部
        header_rect = QRect(0, 0, self.width(), 40)
        painter.fillRect(header_rect, header_gradient)
        
        # 绘制卡牌名称
        painter.setPen(Qt.white)
        font = QFont("Arial", 12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(header_rect, Qt.AlignCenter, self.card.name)
        
        # 绘制HP和ATK
        painter.setFont(QFont("Arial", 18, QFont.Bold))
        painter.setPen(QColor(0, 123, 255))
        
        # HP
        hp_rect = QRect(30, 50, 60, 40)
        painter.drawText(hp_rect, Qt.AlignCenter, str(self.card.HP))
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor(102, 102, 102))
        painter.drawText(30, 90, 60, 20, Qt.AlignCenter, "HP")
        
        # ATK
        painter.setFont(QFont("Arial", 18, QFont.Bold))
        painter.setPen(QColor(0, 123, 255))
        atk_rect = QRect(90, 50, 60, 40)
        painter.drawText(atk_rect, Qt.AlignCenter, str(self.card.ATK))
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor(102, 102, 102))
        painter.drawText(90, 90, 60, 20, Qt.AlignCenter, "ATK")
        
        # 绘制属性标签
        y_offset = 110
        
        if self.card.race:
            painter.setPen(QPen(QColor(212, 237, 218), 1))
            painter.setBrush(QColor(212, 237, 218))
            race_rect = QRect(20, y_offset, 140, 20)
            painter.drawRoundedRect(race_rect, 4, 4)
            painter.setPen(QColor(21, 87, 36))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(race_rect, Qt.AlignCenter, self.card.race)
            y_offset += 25
        
        if self.card.property:
            painter.setPen(QPen(QColor(209, 236, 241), 1))
            painter.setBrush(QColor(209, 236, 241))
            prop_rect = QRect(20, y_offset, 140, 20)
            painter.drawRoundedRect(prop_rect, 4, 4)
            painter.setPen(QColor(12, 84, 96))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(prop_rect, Qt.AlignCenter, self.card.property)
            y_offset += 25
        
        # 绘制费用
        cost_y = self.height() - 25
        painter.setPen(QColor(108, 117, 125))
        painter.setFont(QFont("Arial", 9))
        
        cost_text = "费用: "
        if self.card.cost and len(self.card.cost) > 0:
            if isinstance(self.card.cost, list):
                cost_items = []
                for item in self.card.cost:
                    if isinstance(item, dict):
                        resource = item.get('resource', '')
                        amount = item.get('amount', '')
                        cost_items.append(f"{resource}: {amount}")
                    else:
                        cost_items.append(str(item))
                cost_text += ", ".join(cost_items)
            elif isinstance(self.card.cost, dict):
                cost_items = [f"{k}: {v}" for k, v in self.card.cost.items()]
                cost_text += ", ".join(cost_items)
        else:
            cost_text += "无"
            
        painter.drawText(10, cost_y, self.width()-20, 20, Qt.AlignCenter, cost_text)

class SlotWidget(QWidget):
    """栏位控件"""
    def __init__(self, slot_index: int, is_opponent=False, parent=None):
        super().__init__(parent)
        self.slot_index = slot_index
        self.is_opponent = is_opponent
        self.cards = []
        
        self.setAcceptDrops(not is_opponent)
        self.setMinimumHeight(180)
        
        # 设置样式
        if is_opponent:
            self.setStyleSheet("""
                QWidget {
                    border: 3px solid #6c757d;
                    border-radius: 8px;
                    background-color: #f8f9fa;
                }
            """)
        else:
            self.setStyleSheet("""
                QWidget {
                    border: 3px dashed #adb5bd;
                    border-radius: 8px;
                    background-color: white;
                }
                QWidget:hover {
                    border-color: #28a745;
                    background-color: rgba(40, 167, 69, 0.1);
                }
            """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        
    def dragEnterEvent(self, event):
        if not self.is_opponent and event.mimeData().hasFormat("application/x-card"):
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        if not self.is_opponent:
            mime_data = event.mimeData()
            if mime_data.hasFormat("application/x-card"):
                card_data = json.loads(mime_data.data("application/x-card").data().decode())
                parent = self.parent().parent().parent()  # 获取主窗口
                if hasattr(parent, 'add_card_to_slot'):
                    parent.add_card_to_slot(self.slot_index, card_data)
                event.acceptProposedAction()

class SpecialActionWidget(QWidget):
    """特殊操作控件"""
    def __init__(self, action_type: str, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.action_type = action_type
        
        self.setFixedSize(180, 240)
        self.setCursor(Qt.PointingHandCursor)
        
        # 设置样式
        border_color = "#ff6b6b" if action_type == "squirrels" else "#4ecdc4"
        hover_color = "#fff0f0" if action_type == "squirrels" else "#f0fafa"
        
        self.setStyleSheet(f"""
            QWidget {{
                border: 3px dashed {border_color};
                border-radius: 8px;
                background-color: white;
            }}
            QWidget:hover {{
                background-color: {hover_color};
                border-color: {border_color}80;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)
        
        # 图标
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Arial", 48))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        
        # 标题
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        
        # 描述
        desc_label = QLabel(desc)
        desc_label.setFont(QFont("Arial", 10))
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            parent = self.parent().parent().parent()  # 获取主窗口
            if hasattr(parent, 'send_special_action'):
                parent.send_special_action(self.action_type)

# ======================= 主窗口类 =======================
class XEMKGame(QMainWindow):
    """游戏主窗口"""
    def __init__(self):
        super().__init__()
        
        # 初始化游戏状态
        self.player_id = "player1"
        self.server_ip = "10.2.3.31"
        self.websocket = None
        self.connected = False
        self.is_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
        self.cards = []
        self.current_round_slots = [[], [], [], []]
        self.opponent_current_round_slots = [[], [], [], []]
        self.card_usage_map = {}
        self.round = 0
        self.current_round = 0
        
        # 从命令行参数获取玩家ID
        if len(sys.argv) > 1:
            self.player_id = sys.argv[1]
        
        # 初始化UI
        self.init_ui()
        
        # 连接WebSocket
        self.connect_websocket()
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("🃏 XEMK")
        self.setGeometry(100, 100, 1400, 1000)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("🃏 XEMK")
        title_label.setFont(QFont("Arial", 24, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #333;")
        main_layout.addWidget(title_label)
        
        # 连接设置区域
        config_group = QGroupBox("⚙️ 连接设置")
        config_group.setStyleSheet("""
            QGroupBox {
                background-color: #fff3cd;
                border: 1px solid #ffeaa7;
                border-radius: 5px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        config_layout = QVBoxLayout(config_group)
        
        # IP地址设置
        ip_layout = QHBoxLayout()
        ip_label = QLabel("游戏服务器IP地址:")
        self.ip_input = QLineEdit(self.server_ip)
        self.ip_input.setFixedWidth(200)
        update_btn = QPushButton("更新连接")
        update_btn.clicked.connect(self.update_connection)
        
        ip_layout.addWidget(ip_label)
        ip_layout.addWidget(self.ip_input)
        ip_layout.addWidget(update_btn)
        ip_layout.addStretch()
        config_layout.addLayout(ip_layout)
        
        # 提示文本
        tip_label = QLabel("提示: 在ROS 2主机上运行 <code>hostname -I</code> 查看IP地址")
        tip_label.setStyleSheet("font-size: 12px; color: #666;")
        config_layout.addWidget(tip_label)
        
        # 特殊操作区域
        self.special_actions_container = QWidget()
        self.special_actions_container.setVisible(False)
        special_layout = QVBoxLayout(self.special_actions_container)
        
        special_title = QLabel("⚡ 特殊操作")
        special_title.setFont(QFont("Arial", 12, QFont.Bold))
        special_title.setAlignment(Qt.AlignCenter)
        special_title.setStyleSheet("color: #333; margin-bottom: 10px;")
        special_layout.addWidget(special_title)
        
        # 特殊操作按钮
        actions_layout = QHBoxLayout()
        actions_layout.setAlignment(Qt.AlignCenter)
        actions_layout.setSpacing(20)
        
        self.special_action1 = SpecialActionWidget("squirrels", "🔵", "松鼠", "选择松鼠牌")
        self.special_action2 = SpecialActionWidget("creations", "🔴", "造物", "选择造物牌")
        
        actions_layout.addWidget(self.special_action1)
        actions_layout.addWidget(self.special_action2)
        special_layout.addLayout(actions_layout)
        config_layout.addWidget(self.special_actions_container)
        
        main_layout.addWidget(config_group)
        
        # 连接状态
        self.status_label = QLabel("准备连接...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                padding: 10px;
                border-radius: 5px;
                background-color: #d1ecf1;
                color: #0c5460;
                border: 1px solid #bee5eb;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.status_label)
        
        # 玩家卡牌区域
        player_group = QGroupBox("🃏 Your Cards")
        player_group.setStyleSheet("""
            QGroupBox {
                border: 2px solid #333;
                border-radius: 8px;
                padding-top: 10px;
            }
        """)
        player_layout = QVBoxLayout(player_group)
        
        # 卡牌网格
        self.cards_scroll = QScrollArea()
        self.cards_widget = QWidget()
        self.cards_grid = QHBoxLayout(self.cards_widget)
        self.cards_grid.setSpacing(15)
        self.cards_grid.setContentsMargins(10, 10, 10, 10)
        
        self.cards_scroll.setWidget(self.cards_widget)
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFixedHeight(300)
        
        player_layout.addWidget(self.cards_scroll)
        
        # 当前回合卡牌区域
        current_round_group = QGroupBox("当前回合要使用的卡牌")
        current_round_group.setStyleSheet("""
            QGroupBox {
                background-color: #f8f9fa;
                border: 2px dashed #dee2e6;
                border-radius: 8px;
                padding-top: 10px;
            }
        """)
        current_round_layout = QVBoxLayout(current_round_group)
        
        # 栏位容器
        slots_widget = QWidget()
        slots_layout = QHBoxLayout(slots_widget)
        slots_layout.setSpacing(5)
        
        self.slots = []
        for i in range(4):
            slot_column = QWidget()
            column_layout = QVBoxLayout(slot_column)
            column_layout.setSpacing(10)
            
            slot_title = QLabel(f"栏位 {i+1}")
            slot_title.setFont(QFont("Arial", 12, QFont.Bold))
            slot_title.setAlignment(Qt.AlignCenter)
            slot_title.setFixedHeight(40)
            slot_title.setStyleSheet("color: #495057;")
            
            slot_widget = SlotWidget(i)
            
            column_layout.addWidget(slot_title)
            column_layout.addWidget(slot_widget)
            slots_layout.addWidget(slot_column)
            
            self.slots.append(slot_widget)
        
        current_round_layout.addWidget(slots_widget)
        player_layout.addWidget(current_round_group)
        
        # 对方当前回合卡牌区域
        opponent_group = QGroupBox("对方当前回合使用的卡牌")
        opponent_group.setStyleSheet("""
            QGroupBox {
                background-color: #e9ecef;
                border: 2px solid #ced4da;
                border-radius: 8px;
                padding-top: 10px;
            }
        """)
        opponent_layout = QVBoxLayout(opponent_group)
        
        # 对方栏位容器
        opponent_slots_widget = QWidget()
        opponent_slots_layout = QHBoxLayout(opponent_slots_widget)
        opponent_slots_layout.setSpacing(5)
        
        self.opponent_slots = []
        for i in range(4):
            slot_column = QWidget()
            column_layout = QVBoxLayout(slot_column)
            column_layout.setSpacing(10)
            
            slot_title = QLabel(f"栏位 {i+1}")
            slot_title.setFont(QFont("Arial", 12, QFont.Bold))
            slot_title.setAlignment(Qt.AlignCenter)
            slot_title.setFixedHeight(40)
            slot_title.setStyleSheet("color: #495057;")
            
            slot_widget = SlotWidget(i, is_opponent=True)
            
            column_layout.addWidget(slot_title)
            column_layout.addWidget(slot_widget)
            opponent_slots_layout.addWidget(slot_column)
            
            self.opponent_slots.append(slot_widget)
        
        opponent_layout.addWidget(opponent_slots_widget)
        player_layout.addWidget(opponent_group)
        
        # 控制按钮
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setAlignment(Qt.AlignCenter)
        controls_layout.setSpacing(10)
        
        self.join_btn = QPushButton("加入游戏")
        self.join_btn.clicked.connect(self.join_game)
        self.join_btn.setStyleSheet("""
            QPushButton {
                padding: 12px 24px;
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        self.restart_btn = QPushButton("重新开始")
        self.restart_btn.clicked.connect(self.restart_game)
        self.restart_btn.setStyleSheet("""
            QPushButton {
                padding: 12px 24px;
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        
        self.play_btn = QPushButton("结束己方回合")
        self.play_btn.clicked.connect(self.play_current_round_cards)
        self.play_btn.setEnabled(False)
        self.play_btn.setStyleSheet("""
            QPushButton {
                padding: 12px 24px;
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        controls_layout.addWidget(self.join_btn)
        controls_layout.addWidget(self.restart_btn)
        controls_layout.addWidget(self.play_btn)
        player_layout.addWidget(controls_widget)
        
        main_layout.addWidget(player_group)
        
        # 游戏日志区域
        log_group = QGroupBox("📝 游戏日志")
        log_group.setStyleSheet("""
            QGroupBox {
                border: 2px solid #333;
                border-radius: 8px;
                padding-top: 10px;
            }
        """)
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-family: monospace;
                background-color: #f8f9fa;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)
        
        # 设置主窗口布局
        central_widget.setLayout(main_layout)
    
    def connect_websocket(self):
        """连接WebSocket服务器"""
        threading.Thread(target=self._websocket_thread, daemon=True).start()
    
    def _websocket_thread(self):
        """WebSocket线程"""
        asyncio.run(self._websocket_loop())
    
    async def _websocket_loop(self):
        """WebSocket主循环"""
        while True:
            try:
                self.server_ip = self.ip_input.text() or "10.2.3.31"
                uri = f"ws://{self.server_ip}:8002"
                
                # 更新状态
                self.update_status(f"🔗 正在连接到 {self.server_ip}:8002", "info")
                self.add_to_log(f"尝试连接到 {uri}")
                
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    self.connected = True
                    self.is_connected = True
                    self.reconnect_attempts = 0
                    
                    # 更新状态
                    self.update_status("✅ 已连接到游戏服务器", "success")
                    self.add_to_log(f"已连接到游戏服务器 {self.server_ip}")
                    
                    # 接收消息循环
                    while True:
                        try:
                            message = await websocket.recv()
                            await self.handle_message(message)
                        except websockets.exceptions.ConnectionClosed:
                            self.connected = False
                            self.is_connected = False
                            break
                            
            except Exception as e:
                self.connected = False
                self.is_connected = False
                self.handle_reconnect_error(str(e))
                
            await asyncio.sleep(1)
    
    async def handle_message(self, message):
        """处理服务器消息"""
        try:
            data = json.loads(message)
            print(f"收到消息: {data}")
            
            message_type = data.get('type')
            
            if message_type == 'numbers_assigned':
                await self.handle_numbers_assigned(data)
            elif message_type == 'game_start':
                await self.handle_game_start(data)
            elif message_type == 'move_accepted':
                await self.handle_move_accepted(data)
            elif message_type == 'opponent_move':
                await self.handle_opponent_move(data)
            elif message_type == 'special_action_request':
                await self.handle_special_action_request(data)
            elif message_type == 'opponent_disconnected':
                self.add_to_log(f"⚠️ {data.get('message', '')}")
            elif message_type == 'opponent_reconnected':
                self.add_to_log(f"🔗 {data.get('message', '')}")
            elif message_type == 'waiting_for_opponent':
                self.add_to_log(f"⏳ {data.get('message', '')}")
                
        except Exception as e:
            self.add_to_log(f"解析服务器消息时出错: {str(e)}")
    
    async def handle_numbers_assigned(self, data):
        """处理卡牌分配"""
        self.cards = []
        for card_data in data.get('cards', []):
            card = Card(card_data)
            self.cards.append(card)
        
        # 重置卡牌使用状态
        self.card_usage_map.clear()
        for i, card in enumerate(self.cards):
            unique_id = f"{card.name}_{i}"
            self.card_usage_map[unique_id] = CardUsage(card)
        
        # 更新UI
        self.render_cards()
        self.update_current_round_display()
        self.update_opponent_current_round_display()
        
        # 更新状态
        self.update_status("✅ 卡牌分配完成! 游戏准备就绪", "success")
        
        # 显示卡牌名称
        card_names = ", ".join([card.name for card in self.cards])
        self.add_to_log(f"你获得了 {len(self.cards)} 张卡牌: {card_names}")
        
        # 更新回合信息
        if self.round % 2 == 0:
            self.current_round = self.round // 2
            self.add_to_log(f"回合 {self.current_round}")
        self.round += 1
        
        # 启用结束回合按钮
        self.play_btn.setEnabled(True)
    
    async def handle_game_start(self, data):
        """处理游戏开始"""
        self.add_to_log('🎮 游戏开始! 双方玩家已就位')
        last_player = data.get('last_player', '')
        self.add_to_log(f"上次出牌: {last_player}")
        
        # 重置游戏状态
        self.card_usage_map.clear()
        self.current_round_slots = [[], [], [], []]
        self.opponent_current_round_slots = [[], [], [], []]
        
        # 更新UI
        self.render_cards()
        self.update_current_round_display()
        self.update_opponent_current_round_display()
    
    async def handle_move_accepted(self, data):
        """处理移动确认"""
        message = data.get('message', '')
        self.add_to_log(f"✅ {message}")
        
        cards_played = data.get('cards_played', [])
        self.add_to_log(f"收到服务器确认，卡牌数量: {len(cards_played)}")
        
        # 清空当前回合所有栏位
        self.current_round_slots = [[], [], [], []]
        
        # 重置卡牌使用状态
        for usage in self.card_usage_map.values():
            usage.used = False
            usage.slot_index = -1
        
        # 更新UI
        self.render_cards()
        self.update_current_round_display()
        self.add_to_log("服务器确认，栏位已更新")
    
    async def handle_opponent_move(self, data):
        """处理对方移动"""
        cards_played = data.get('cards_played', [])
        
        if cards_played and len(cards_played) > 0:
            # 获取卡牌名称列表（跳过null值）
            valid_cards = [card for card in cards_played if card]
            card_names = ", ".join([card.get('name', '') for card in valid_cards])
            
            # 更新日志
            self.add_to_log(f"对方打出卡牌: {card_names}")
            
            # 清空对方栏位
            self.opponent_current_round_slots = [[], [], [], []]
            
            # 解析卡牌到栏位
            current_slot_index = 0
            cards_in_current_slot = 0
            
            for card_data in cards_played:
                if card_data is None:
                    continue
                
                if current_slot_index < 4:
                    card = Card(card_data)
                    self.opponent_current_round_slots[current_slot_index].append(card)
                    cards_in_current_slot += 1
                    
                    # 假设每个栏位最多放置2张卡牌
                    if cards_in_current_slot >= 2:
                        current_slot_index += 1
                        cards_in_current_slot = 0
            
            # 如果有明确的栏位分配信息
            slots = data.get('slots', [])
            if slots and isinstance(slots, list):
                self.add_to_log("使用明确的栏位分配信息")
                for i in range(min(len(slots), 4)):
                    self.opponent_current_round_slots[i] = []
                    for card_data in slots[i]:
                        card = Card(card_data)
                        self.opponent_current_round_slots[i].append(card)
            
            # 更新UI
            self.update_opponent_current_round_display()
    
    async def handle_special_action_request(self, data):
        """处理特殊操作请求"""
        instruction = data.get('instruction', '请选择操作')
        self.show_special_actions(instruction)
    
    def show_special_actions(self, instruction):
        """显示特殊操作按钮"""
        self.special_actions_container.setVisible(True)
        
        # 更新标题
        for child in self.special_actions_container.findChildren(QLabel):
            if child.text().startswith("⚡"):
                child.setText(f"⚡ {instruction}")
        
        self.add_to_log(f"收到特殊操作指令: {instruction}")
    
    def hide_special_actions(self):
        """隐藏特殊操作按钮"""
        self.special_actions_container.setVisible(False)
    
    def send_special_action(self, action_type):
        """发送特殊操作"""
        if self.connected and self.websocket:
            action_msg = {
                'type': 'special_action',
                'player_id': self.player_id,
                'action_type': action_type
            }
            
            asyncio.run_coroutine_threadsafe(
                self.send_websocket_message(action_msg),
                asyncio.get_event_loop()
            )
            
            self.add_to_log(f"发送特殊操作: {action_type}")
            self.hide_special_actions()
    
    async def send_websocket_message(self, message):
        """发送WebSocket消息"""
        if self.websocket:
            await self.websocket.send(json.dumps(message))
            print(f"发送消息: {message}")
    
    def render_cards(self):
        """渲染卡牌"""
        # 清除现有卡牌
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.cards:
            no_cards_label = QLabel("No cards yet. Join the game first.")
            no_cards_label.setAlignment(Qt.AlignCenter)
            no_cards_label.setStyleSheet("color: #666; padding: 20px;")
            self.cards_grid.addWidget(no_cards_label)
            return
        
        # 添加卡牌
        for i, card in enumerate(self.cards):
            unique_id = f"{card.name}_{i}"
            
            # 获取使用状态
            usage = self.card_usage_map.get(unique_id)
            if not usage:
                usage = CardUsage(card)
                self.card_usage_map[unique_id] = usage
            
            # 创建卡牌控件
            card_widget = CardWidget(card)
            card_widget.is_used = usage.used
            
            # 设置鼠标事件
            card_widget.mousePressEvent = lambda event, widget=card_widget, idx=i, uid=unique_id: self.on_card_click(event, widget, idx, uid)
            
            # 允许拖动
            card_widget.setAcceptDrops(False)
            
            self.cards_grid.addWidget(card_widget)
    
    def on_card_click(self, event, widget, index, unique_id):
        """处理卡牌点击"""
        if event.button() == Qt.LeftButton:
            # 开始拖动
            drag = QDrag(widget)
            mime_data = QMimeData()
            
            card_data = {
                'card': {
                    'name': widget.card.name,
                    'HP': widget.card.HP,
                    'ATK': widget.card.ATK,
                    'property': widget.card.property,
                    'race': widget.card.race,
                    'cost': widget.card.cost,
                    'card_id': widget.card.card_id
                },
                'index': index,
                'uniqueId': unique_id
            }
            
            mime_data.setData("application/x-card", json.dumps(card_data).encode())
            drag.setMimeData(mime_data)
            
            # 设置拖动时的视觉效果
            widget.is_dragging = True
            widget.update()
            
            # 执行拖动
            drag.exec_(Qt.CopyAction)
            
            # 重置拖动状态
            widget.is_dragging = False
            widget.update()
            
        elif event.button() == Qt.RightButton:
            # 右键显示详情
            self.show_card_detail(widget.card)
    
    def add_card_to_slot(self, slot_index, card_data):
        """添加卡牌到栏位"""
        unique_id = card_data['uniqueId']
        
        # 检查卡牌是否已被使用
        if unique_id not in self.card_usage_map:
            return False
        
        usage = self.card_usage_map[unique_id]
        
        # 如果卡牌已被使用，先从原栏位移除
        if usage.used and usage.slot_index != slot_index:
            self.remove_card_from_slot(usage.slot_index, unique_id)
        
        # 如果已经在同一个栏位，不需要重复添加
        if usage.used and usage.slot_index == slot_index:
            return True
        
        # 添加到指定栏位
        card = Card(card_data['card'])
        self.current_round_slots[slot_index].append({
            'card': card,
            'unique_id': unique_id,
            'slot_index': slot_index
        })
        
        # 更新卡牌使用状态
        usage.used = True
        usage.slot_index = slot_index
        
        # 发送放置更新给对手
        self.send_card_placement_update(slot_index, card_data['card'], 'add')
        
        # 更新UI
        self.update_current_round_display()
        self.render_cards()
        return True
    
    def remove_card_from_slot(self, slot_index, specific_unique_id=None):
        """从栏位移除卡牌"""
        if not self.current_round_slots[slot_index]:
            return
        
        if specific_unique_id:
            # 移除特定卡牌
            for i, card_data in enumerate(self.current_round_slots[slot_index]):
                if card_data['unique_id'] == specific_unique_id:
                    removed_card = self.current_round_slots[slot_index].pop(i)
                    
                    # 更新卡牌使用状态
                    if removed_card['unique_id'] in self.card_usage_map:
                        usage = self.card_usage_map[removed_card['unique_id']]
                        usage.used = False
                        usage.slot_index = -1
                    
                    # 发送移除更新
                    self.send_card_placement_update(slot_index, {
                        'name': removed_card['card'].name,
                        'HP': removed_card['card'].HP,
                        'ATK': removed_card['card'].ATK,
                        'property': removed_card['card'].property,
                        'race': removed_card['card'].race,
                        'cost': removed_card['card'].cost,
                        'card_id': removed_card['card'].card_id
                    }, 'remove')
                    break
        else:
            # 移除整个栏位的所有卡牌
            removed_cards = self.current_round_slots[slot_index].copy()
            self.current_round_slots[slot_index] = []
            
            # 更新所有卡牌的使用状态
            for card_data in removed_cards:
                if card_data['unique_id'] in self.card_usage_map:
                    usage = self.card_usage_map[card_data['unique_id']]
                    usage.used = False
                    usage.slot_index = -1
            
            # 发送清空更新
            self.send_card_placement_update(slot_index, None, 'clear')
        
        # 更新UI
        self.update_current_round_display()
        self.render_cards()
    
    def update_current_round_display(self):
        """更新当前回合显示"""
        for i, slot in enumerate(self.slots):
            # 清除现有内容
            while slot.layout.count():
                item = slot.layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            cards = self.current_round_slots[i]
            
            if not cards:
                # 添加空栏位提示
                empty_label = QLabel("拖放或点击卡牌到这里")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("color: #adb5bd; font-style: italic; padding: 20px;")
                slot.layout.addWidget(empty_label)
            else:
                # 添加卡牌
                for card_data in cards:
                    card_widget = CardWidget(card_data['card'])
                    card_widget.setFixedSize(170, 220)
                    card_widget.is_used = True
                    
                    # 添加移除按钮
                    remove_btn = QPushButton("×")
                    remove_btn.setFixedSize(24, 24)
                    remove_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #ffc107;
                            color: white;
                            border: none;
                            border-radius: 12px;
                            font-size: 14px;
                        }
                        QPushButton:hover {
                            background-color: #e0a800;
                        }
                    """)
                    remove_btn.clicked.connect(lambda checked, s=i, uid=card_data['unique_id']: 
                                              self.remove_card_from_slot(s, uid))
                    
                    # 创建容器
                    container = QWidget()
                    container_layout = QVBoxLayout(container)
                    container_layout.setContentsMargins(0, 0, 0, 0)
                    container_layout.setAlignment(Qt.AlignTop)
                    
                    container_layout.addWidget(card_widget)
                    container_layout.addWidget(remove_btn, 0, Qt.AlignRight)
                    
                    slot.layout.addWidget(container)
            
            # 更新布局
            slot.layout.addStretch()
    
    def update_opponent_current_round_display(self):
        """更新对手当前回合显示"""
        for i, slot in enumerate(self.opponent_slots):
            # 清除现有内容
            while slot.layout.count():
                item = slot.layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            cards = self.opponent_current_round_slots[i]
            
            if not cards:
                # 添加空栏位提示
                empty_label = QLabel("等待对方出牌")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("color: #adb5bd; font-style: italic; padding: 20px;")
                slot.layout.addWidget(empty_label)
            else:
                # 添加卡牌
                for card in cards:
                    card_widget = CardWidget(card)
                    card_widget.setFixedSize(170, 220)
                    card_widget.setStyleSheet("opacity: 0.9;")
                    card_widget.is_used = True
                    
                    slot.layout.addWidget(card_widget)
            
            # 更新布局
            slot.layout.addStretch()
    
    def play_current_round_cards(self):
        """结束当前回合"""
        if not self.connected:
            self.add_to_log('❌连接失败')
            return
        
        # 收集所有栏位的卡牌
        all_cards = []
        for i in range(len(self.current_round_slots)):
            for card_data in self.current_round_slots[i]:
                card = card_data['card']
                all_cards.append({
                    'name': card.name,
                    'HP': card.HP,
                    'ATK': card.ATK,
                    'property': card.property,
                    'race': card.race,
                    'cost': card.cost,
                    'id': card.card_id
                })
        
        if len(all_cards) == 0:
            self.add_to_log('已结束，没有出牌')
            self.play_btn.setEnabled(False)
            return
        
        # 记录哪些卡牌被打出了
        played_unique_ids = []
        for i in range(len(self.current_round_slots)):
            for card_data in self.current_round_slots[i]:
                played_unique_ids.append(card_data['unique_id'])
        
        # 准备消息
        play_msg = {
            'type': 'player_action',
            'player_id': self.player_id,
            'cards': [card['name'] for card in all_cards],
            'slots': [
                [
                    {
                        'name': card_data['card'].name,
                        'HP': card_data['card'].HP,
                        'ATK': card_data['card'].ATK,
                        'property': card_data['card'].property,
                        'race': card_data['card'].race,
                        'id': card_data['card'].card_id
                    }
                    for card_data in self.current_round_slots[i]
                ]
                for i in range(4)
            ],
            'card_details': all_cards
        }
        
        # 发送消息
        asyncio.run_coroutine_threadsafe(
            self.send_websocket_message(play_msg),
            asyncio.get_event_loop()
        )
        
        card_names = ", ".join([card['name'] for card in all_cards])
        self.add_to_log(f"打出卡牌: {card_names}")
        
        # 从卡牌列表中永久移除打出的卡牌
        self.cards = [
            card for i, card in enumerate(self.cards)
            if f"{card.name}_{i}" not in played_unique_ids
        ]
        
        # 清除使用状态
        for uid in played_unique_ids:
            if uid in self.card_usage_map:
                del self.card_usage_map[uid]
        
        # 重置当前回合栏位
        self.current_round_slots = [[], [], [], []]
        
        # 更新UI
        self.update_current_round_display()
        self.render_cards()
        
        # 禁用出牌按钮
        self.play_btn.setEnabled(False)
    
    def send_card_placement_update(self, slot_index, card_data, action):
        """发送卡牌放置更新"""
        if self.connected and self.websocket:
            update_msg = {
                'type': 'card_placement_update',
                'player_id': self.player_id,
                'slot_index': slot_index,
                'card': card_data,
                'action': action
            }
            
            asyncio.run_coroutine_threadsafe(
                self.send_websocket_message(update_msg),
                asyncio.get_event_loop()
            )
    
    def show_card_detail(self, card):
        """显示卡牌详情"""
        dialog = QDialog(self)
        dialog.setWindowTitle("卡牌详情")
        dialog.setFixedSize(400, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 标题
        title_label = QLabel(card.name)
        title_label.setFont(QFont("Arial", 20, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                background: linear-gradient(135deg, #007bff, #0056b3);
                color: white;
                padding: 15px;
                border-radius: 5px 5px 0 0;
            }
        """)
        layout.addWidget(title_label)
        
        # 关闭按钮
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                color: white;
                font-size: 24px;
            }
        """)
        close_btn.clicked.connect(dialog.accept)
        
        # 将关闭按钮放在标题上
        close_btn.move(360, 10)
        
        # 详细信息
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setSpacing(10)
        
        # HP
        hp_widget = self.create_detail_row("生命值 (HP)", str(card.HP))
        detail_layout.addWidget(hp_widget)
        
        # ATK
        atk_widget = self.create_detail_row("攻击力 (ATK)", str(card.ATK))
        detail_layout.addWidget(atk_widget)
        
        # 属性
        property_text = card.property if card.property else "无"
        prop_widget = self.create_detail_row("属性", property_text)
        detail_layout.addWidget(prop_widget)
        
        # 种族
        race_text = card.race if card.race else "无"
        race_widget = self.create_detail_row("种族", race_text)
        detail_layout.addWidget(race_widget)
        
        # 费用
        cost_text = "无"
        if card.cost and len(card.cost) > 0:
            if isinstance(card.cost, list):
                cost_items = []
                for item in card.cost:
                    if isinstance(item, dict):
                        resource = item.get('resource', '')
                        amount = item.get('amount', '')
                        cost_items.append(f"{resource}: {amount}")
                    else:
                        cost_items.append(str(item))
                cost_text = ", ".join(cost_items)
            elif isinstance(card.cost, dict):
                cost_items = [f"{k}: {v}" for k, v in card.cost.items()]
                cost_text = ", ".join(cost_items)
        
        cost_widget = self.create_detail_row("费用", cost_text)
        detail_layout.addWidget(cost_widget)
        
        layout.addWidget(detail_widget)
        
        dialog.exec_()
    
    def create_detail_row(self, label, value):
        """创建详情行"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 10, 20, 10)
        
        label_widget = QLabel(label)
        label_widget.setFont(QFont("Arial", 10, QFont.Bold))
        label_widget.setStyleSheet("color: #495057;")
        
        value_widget = QLabel(value)
        value_widget.setFont(QFont("Arial", 12))
        
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)
        
        # 添加分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #eee;")
        layout.addWidget(line)
        
        return widget
    
    def join_game(self):
        """加入游戏"""
        if self.connected and self.websocket:
            join_msg = {
                'type': 'player_join',
                'player_id': self.player_id
            }
            
            asyncio.run_coroutine_threadsafe(
                self.send_websocket_message(join_msg),
                asyncio.get_event_loop()
            )
            
            self.add_to_log(f"以 {self.player_id} 身份加入游戏...")
            self.join_btn.setEnabled(False)
        else:
            self.update_status("❌ 未连接到服务器", "error")
            self.add_to_log("无法加入: WebSocket 未连接")
    
    def restart_game(self):
        """重新开始游戏"""
        if self.connected and self.websocket:
            restart_msg = {
                'type': 'start_new_round',
                'player_id': self.player_id
            }
            
            asyncio.run_coroutine_threadsafe(
                self.send_websocket_message(restart_msg),
                asyncio.get_event_loop()
            )
            
            self.add_to_log("请求新的游戏回合...")
        else:
            self.update_status("❌ 未连接到服务器", "error")
            self.add_to_log("无法请求新回合: WebSocket 未连接")
    
    def update_status(self, message, status_type):
        """更新状态显示"""
        self.status_label.setText(message)
        
        if status_type == 'success':
            style = "background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb;"
        elif status_type == 'error':
            style = "background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;"
        else:  # info
            style = "background-color: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb;"
        
        self.status_label.setStyleSheet(f"QLabel {{ padding: 10px; border-radius: 5px; {style} font-weight: bold; }}")
    
    def add_to_log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    def handle_reconnect_error(self, error_msg):
        """处理重连错误"""
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            delay = min(1000 * self.reconnect_attempts, 10000)
            
            self.update_status(
                f"🔄 重新连接中... (尝试 {self.reconnect_attempts}/{self.max_reconnect_attempts})",
                "info"
            )
            self.add_to_log(f"连接失败，{delay//1000}秒后重试...")
            
            QTimer.singleShot(delay, self.connect_websocket)
        else:
            self.update_status("❌ 连接失败，请检查服务器状态和IP地址", "error")
            self.add_to_log("达到最大重试次数，连接失败")
    
    def update_connection(self):
        """更新连接"""
        self.server_ip = self.ip_input.text() or "10.2.3.31"
        self.reconnect_attempts = 0
        self.connect_websocket()

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle("Fusion")
    
    # 创建游戏客户端
    client = XEMKGame()
    client.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()