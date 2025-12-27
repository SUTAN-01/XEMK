import sys
import json
import asyncio
import websockets
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import threading
import time

@dataclass
class Card:
    """卡牌数据类"""
    name: str
    HP: int
    ATK: int
    property: str = ""
    race: str = ""
    cost: List[Dict[str, Any]] = None
    card_id: str = ""
    
    def __post_init__(self):
        if self.cost is None:
            self.cost = []

@dataclass
class CardUsage:
    """卡牌使用状态"""
    card: Card
    used: bool = False
    slot_index: int = -1

class CardWidget(QWidget):
    """卡牌控件"""
    def __init__(self, card: Card, card_index: int, parent=None):
        super().__init__(parent)
        self.card = card
        self.card_index = card_index
        self.unique_id = f"{card.name}_{card_index}"
        self.is_dragging = False
        self.is_used = False
        self.is_slot_card = False
        
        self.setFixedSize(180, 240)
        self.setCursor(Qt.PointingHandCursor)
        
        # 设置样式
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 2px solid #007bff;
                border-radius: 8px;
            }
            QWidget[used="true"] {
                opacity: 0.5;
                background-color: #f5f5f5;
                border-color: #6c757d;
            }
        """)
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        # 鼠标跟踪
        self.setMouseTracking(True)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制卡牌背景
        if self.is_used:
            painter.fillRect(self.rect(), QColor(245, 245, 245))
        else:
            painter.fillRect(self.rect(), Qt.white)
        
        # 绘制边框
        border_color = QColor(108, 117, 125) if self.is_used else QColor(0, 123, 255)
        if self.is_dragging:
            border_color = border_color.darker(120)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(1, 1, self.width()-2, self.height()-2, 8, 8)
        
        # 绘制卡牌头部
        header_rect = QRect(0, 0, self.width(), 40)
        gradient = QLinearGradient(0, 0, 0, 40)
        if self.is_used:
            gradient.setColorAt(0, QColor(108, 117, 125))
            gradient.setColorAt(1, QColor(73, 80, 87))
        else:
            gradient.setColorAt(0, QColor(0, 123, 255))
            gradient.setColorAt(1, QColor(0, 86, 179))
        painter.fillRect(header_rect, gradient)
        
        # 绘制卡牌名称
        painter.setPen(Qt.white)
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        painter.drawText(header_rect, Qt.AlignCenter, self.card.name)
        
        # 绘制统计数据
        stats_y = 50
        painter.setPen(Qt.black)
        painter.setFont(QFont("Arial", 10))
        
        # HP
        hp_rect = QRect(20, stats_y, 60, 40)
        painter.setFont(QFont("Arial", 18, QFont.Bold))
        painter.setPen(QColor(0, 123, 255))
        painter.drawText(hp_rect, Qt.AlignCenter, str(self.card.HP))
        
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor(102, 102, 102))
        painter.drawText(20, stats_y + 40, 60, 20, Qt.AlignCenter, "HP")
        
        # ATK
        atk_rect = QRect(100, stats_y, 60, 40)
        painter.setFont(QFont("Arial", 18, QFont.Bold))
        painter.setPen(QColor(0, 123, 255))
        painter.drawText(atk_rect, Qt.AlignCenter, str(self.card.ATK))
        
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor(102, 102, 102))
        painter.drawText(100, stats_y + 40, 60, 20, Qt.AlignCenter, "ATK")
        
        # 绘制属性标签
        y_offset = 100
        if self.card.race:
            race_rect = QRect(20, y_offset, 140, 24)
            painter.setPen(QPen(QColor(212, 237, 218), 1))
            painter.setBrush(QColor(212, 237, 218))
            painter.drawRoundedRect(race_rect, 4, 4)
            painter.setPen(QColor(21, 87, 36))
            painter.setFont(QFont("Arial", 9))
            painter.drawText(race_rect, Qt.AlignCenter, self.card.race)
            y_offset += 28
        
        if self.card.property:
            prop_rect = QRect(20, y_offset, 140, 24)
            painter.setPen(QPen(QColor(209, 236, 241), 1))
            painter.setBrush(QColor(209, 236, 241))
            painter.drawRoundedRect(prop_rect, 4, 4)
            painter.setPen(QColor(12, 84, 96))
            painter.setFont(QFont("Arial", 9))
            painter.drawText(prop_rect, Qt.AlignCenter, self.card.property)
        
        # 绘制费用
        cost_y = self.height() - 30
        painter.setPen(QColor(108, 117, 125))
        painter.setFont(QFont("Arial", 9))
        
        cost_text = "费用: "
        if self.card.cost:
            cost_items = []
            for cost_item in self.card.cost:
                if isinstance(cost_item, dict):
                    cost_items.append(f"{cost_item.get('resource', '')}: {cost_item.get('amount', '')}")
                else:
                    cost_items.append(str(cost_item))
            cost_text += ", ".join(cost_items)
        else:
            cost_text += "无"
        
        painter.drawText(10, cost_y, self.width()-20, 20, Qt.AlignCenter, cost_text)

class SlotWidget(QWidget):
    """卡牌放置栏位"""
    def __init__(self, slot_index: int, is_opponent=False, parent=None):
        super().__init__(parent)
        self.slot_index = slot_index
        self.is_opponent = is_opponent
        self.cards = []
        self.is_highlighted = False
        
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
        
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
                QWidget[highlighted="true"] {
                    border-color: #28a745;
                    background-color: rgba(40, 167, 69, 0.1);
                }
            """)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.cards:
            # 如果有卡牌，由卡牌自己绘制
            pass
        else:
            # 绘制空栏位提示
            painter.setPen(QColor(173, 181, 189))
            painter.setFont(QFont("Arial", 10, QFont.StyleItalic))
            
            if self.is_opponent:
                text = "等待对方出牌"
            else:
                text = "拖放卡牌到这里"
                
            painter.drawText(self.rect(), Qt.AlignCenter, text)
    
    def dragEnterEvent(self, event):
        if not self.is_opponent and event.mimeData().hasFormat("application/x-card"):
            event.acceptProposedAction()
            self.setProperty("highlighted", True)
            self.style().polish(self)
    
    def dragLeaveEvent(self, event):
        self.setProperty("highlighted", False)
        self.style().polish(self)
    
    def dropEvent(self, event):
        if self.is_opponent:
            return
            
        mime_data = event.mimeData()
        if mime_data.hasFormat("application/x-card"):
            card_data = json.loads(mime_data.data("application/x-card").data().decode())
            if hasattr(self.parent(), 'add_card_to_slot'):
                self.parent().add_card_to_slot(self.slot_index, card_data)
            
        self.setProperty("highlighted", False)
        self.style().polish(self)

class SpecialActionButton(QWidget):
    """特殊操作按钮"""
    def __init__(self, action_type: str, icon: str, title: str, description: str, parent=None):
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
                border-color: {border_color.replace('#', '#')}80;
            }}
        """)
        
        # 布局
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        # 图标
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Arial", 48))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        
        # 标题
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        
        # 描述
        desc_label = QLabel(description)
        desc_label.setFont(QFont("Arial", 10))
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        self.setLayout(layout)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if hasattr(self.parent(), 'on_special_action'):
                self.parent().on_special_action(self.action_type)

class GameClient(QMainWindow):
    """游戏客户端主窗口"""
    def __init__(self):
        super().__init__()
        
        # 初始化游戏状态
        self.player_id = "player1"
        self.server_ip = "10.2.3.31"
        self.websocket = None
        self.connected = False
        self.cards = []
        self.current_round_slots = [[], [], [], []]
        self.opponent_current_round_slots = [[], [], [], []]
        self.card_usage_map = {}
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
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
        
        # 标题
        title_label = QLabel("🃏 XEMK")
        title_label.setFont(QFont("Arial", 24, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 连接设置区域
        config_group = QGroupBox("⚙️ 连接设置")
        config_layout = QHBoxLayout()
        
        ip_label = QLabel("游戏服务器IP地址:")
        self.ip_input = QLineEdit(self.server_ip)
        self.ip_input.setFixedWidth(200)
        
        update_btn = QPushButton("更新连接")
        update_btn.clicked.connect(self.update_connection)
        
        config_layout.addWidget(ip_label)
        config_layout.addWidget(self.ip_input)
        config_layout.addWidget(update_btn)
        config_layout.addStretch()
        
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)
        
        # 特殊操作区域
        self.special_actions_container = QWidget()
        special_actions_layout = QVBoxLayout(self.special_actions_container)
        
        special_title = QLabel("⚡ 特殊操作")
        special_title.setFont(QFont("Arial", 12, QFont.Bold))
        special_title.setAlignment(Qt.AlignCenter)
        special_actions_layout.addWidget(special_title)
        
        # 特殊操作按钮
        actions_layout = QHBoxLayout()
        actions_layout.setAlignment(Qt.AlignCenter)
        
        self.special_action1 = SpecialActionButton("squirrels", "🔵", "松鼠", "选择松鼠牌", self)
        self.special_action2 = SpecialActionButton("creations", "🔴", "造物", "选择造物牌", self)
        
        actions_layout.addWidget(self.special_action1)
        actions_layout.addWidget(self.special_action2)
        
        special_actions_layout.addLayout(actions_layout)
        self.special_actions_container.setVisible(False)
        main_layout.addWidget(self.special_actions_container)
        
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
            }
        """)
        main_layout.addWidget(self.status_label)
        
        # 玩家卡牌区域
        cards_group = QGroupBox("🃏 Your Cards")
        cards_layout = QVBoxLayout()
        
        # 卡牌网格
        self.cards_scroll = QScrollArea()
        self.cards_widget = QWidget()
        self.cards_grid = QGridLayout(self.cards_widget)
        self.cards_grid.setSpacing(15)
        
        self.cards_scroll.setWidget(self.cards_widget)
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFixedHeight(300)
        
        cards_layout.addWidget(self.cards_scroll)
        
        # 当前回合卡牌区域
        current_round_group = QGroupBox("当前回合要使用的卡牌")
        current_round_layout = QVBoxLayout()
        
        # 栏位容器
        slots_widget = QWidget()
        slots_layout = QHBoxLayout(slots_widget)
        
        self.slots = []
        for i in range(4):
            slot_column = QWidget()
            slot_layout = QVBoxLayout(slot_column)
            
            slot_title = QLabel(f"栏位 {i+1}")
            slot_title.setFont(QFont("Arial", 10, QFont.Bold))
            slot_title.setAlignment(Qt.AlignCenter)
            slot_title.setFixedHeight(40)
            
            slot_widget = SlotWidget(i)
            slot_widget.setProperty("highlighted", False)
            
            slot_layout.addWidget(slot_title)
            slot_layout.addWidget(slot_widget)
            slots_layout.addWidget(slot_column)
            
            self.slots.append(slot_widget)
        
        current_round_layout.addWidget(slots_widget)
        current_round_group.setLayout(current_round_layout)
        cards_layout.addWidget(current_round_group)
        
        # 对方当前回合卡牌区域
        opponent_round_group = QGroupBox("对方当前回合使用的卡牌")
        opponent_round_layout = QVBoxLayout()
        
        opponent_slots_widget = QWidget()
        opponent_slots_layout = QHBoxLayout(opponent_slots_widget)
        
        self.opponent_slots = []
        for i in range(4):
            slot_column = QWidget()
            slot_layout = QVBoxLayout(slot_column)
            
            slot_title = QLabel(f"栏位 {i+1}")
            slot_title.setFont(QFont("Arial", 10, QFont.Bold))
            slot_title.setAlignment(Qt.AlignCenter)
            slot_title.setFixedHeight(40)
            
            slot_widget = SlotWidget(i, is_opponent=True)
            slot_layout.addWidget(slot_title)
            slot_layout.addWidget(slot_widget)
            opponent_slots_layout.addWidget(slot_column)
            
            self.opponent_slots.append(slot_widget)
        
        opponent_round_layout.addWidget(opponent_slots_widget)
        opponent_round_group.setLayout(opponent_round_layout)
        cards_layout.addWidget(opponent_round_group)
        
        # 控制按钮
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setAlignment(Qt.AlignCenter)
        
        self.join_btn = QPushButton("加入游戏")
        self.join_btn.clicked.connect(self.join_game)
        
        self.restart_btn = QPushButton("重新开始")
        self.restart_btn.clicked.connect(self.restart_game)
        
        self.play_btn = QPushButton("结束己方回合")
        self.play_btn.clicked.connect(self.play_current_round_cards)
        self.play_btn.setEnabled(False)
        
        controls_layout.addWidget(self.join_btn)
        controls_layout.addWidget(self.restart_btn)
        controls_layout.addWidget(self.play_btn)
        
        cards_layout.addWidget(controls_widget)
        cards_group.setLayout(cards_layout)
        main_layout.addWidget(cards_group)
        
        # 游戏日志区域
        log_group = QGroupBox("📝 游戏日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-family: monospace;
                background-color: #f8f9fa;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
        """)
        
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
    
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
                uri = f"ws://{self.server_ip}:8002"
                self.update_status(f"🔗 正在连接到 {self.server_ip}:8002", "info")
                self.add_to_log(f"尝试连接到 {uri}")
                
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    self.connected = True
                    self.reconnect_attempts = 0
                    
                    self.update_status("✅ 已连接到游戏服务器", "success")
                    self.add_to_log(f"已连接到游戏服务器 {self.server_ip}")
                    
                    # 接收消息循环
                    while True:
                        try:
                            message = await websocket.recv()
                            self.handle_message(message)
                        except websockets.exceptions.ConnectionClosed:
                            break
                            
            except Exception as e:
                self.connected = False
                self.handle_reconnect_error(str(e))
                
            await asyncio.sleep(1)
    
    def handle_message(self, message):
        """处理服务器消息"""
        try:
            data = json.loads(message)
            print(f"Received: {data}")
            
            message_type = data.get('type')
            
            if message_type == 'numbers_assigned':
                self.handle_numbers_assigned(data)
            elif message_type == 'game_start':
                self.handle_game_start(data)
            elif message_type == 'move_accepted':
                self.handle_move_accepted(data)
            elif message_type == 'opponent_move':
                self.handle_opponent_move(data)
            elif message_type == 'special_action_request':
                self.handle_special_action_request(data)
            elif message_type == 'waiting_for_opponent':
                self.add_to_log(f"⏳ {data.get('message', '')}")
            elif message_type == 'opponent_disconnected':
                self.add_to_log(f"⚠️ {data.get('message', '')}")
            elif message_type == 'opponent_reconnected':
                self.add_to_log(f"🔗 {data.get('message', '')}")
                
        except Exception as e:
            self.add_to_log(f"解析消息时出错: {str(e)}")
    
    def handle_numbers_assigned(self, data):
        """处理卡牌分配"""
        self.cards = []
        for card_data in data.get('cards', []):
            card = Card(
                name=card_data.get('name', ''),
                HP=card_data.get('HP', 0),
                ATK=card_data.get('ATK', 0),
                property=card_data.get('property', ''),
                race=card_data.get('race', ''),
                cost=card_data.get('cost', []),
                card_id=card_data.get('card_id', '')
            )
            self.cards.append(card)
        
        # 重置使用状态
        self.card_usage_map.clear()
        self.current_round_slots = [[], [], [], []]
        
        # 更新UI
        self.render_cards()
        self.update_current_round_display()
        
        self.update_status("✅ 卡牌分配完成! 游戏准备就绪", "success")
        
        card_names = ", ".join([card.name for card in self.cards])
        self.add_to_log(f"你获得了 {len(self.cards)} 张卡牌: {card_names}")
    
    def handle_game_start(self, data):
        """处理游戏开始"""
        self.add_to_log("🎮 游戏开始! 双方玩家已就位")
        last_player = data.get('last_player', '')
        self.add_to_log(f"上次出牌: {last_player}")
        
        self.card_usage_map.clear()
        self.current_round_slots = [[], [], [], []]
        self.opponent_current_round_slots = [[], [], [], []]
        
        self.render_cards()
        self.update_current_round_display()
        self.update_opponent_current_round_display()
    
    def handle_move_accepted(self, data):
        """处理移动确认"""
        message = data.get('message', '')
        self.add_to_log(f"✅ {message}")
        
        cards_played = data.get('cards_played', [])
        self.add_to_log(f"收到服务器确认，卡牌数量: {len(cards_played)}")
        
        # 清空当前回合栏位
        self.current_round_slots = [[], [], [], []]
        
        # 更新卡牌使用状态
        for unique_id in list(self.card_usage_map.keys()):
            if self.card_usage_map[unique_id].used:
                self.card_usage_map[unique_id].used = False
                self.card_usage_map[unique_id].slot_index = -1
        
        self.render_cards()
        self.update_current_round_display()
        self.add_to_log("服务器确认，栏位已更新")
    
    def handle_opponent_move(self, data):
        """处理对方移动"""
        cards_played = data.get('cards_played', [])
        
        if cards_played:
            valid_cards = [card for card in cards_played if card]
            card_names = ", ".join([card.get('name', '') for card in valid_cards])
            self.add_to_log(f"对方打出卡牌: {card_names}")
            
            # 清空对方栏位
            self.opponent_current_round_slots = [[], [], [], []]
            
            # 解析卡牌到栏位
            current_slot = 0
            cards_in_current_slot = 0
            
            for card_data in cards_played:
                if card_data is None:
                    continue
                
                if current_slot < 4:
                    card = Card(
                        name=card_data.get('name', ''),
                        HP=card_data.get('HP', 0),
                        ATK=card_data.get('ATK', 0),
                        property=card_data.get('property', ''),
                        race=card_data.get('race', ''),
                        cost=card_data.get('cost', []),
                        card_id=card_data.get('card_id', '')
                    )
                    self.opponent_current_round_slots[current_slot].append(card)
                    cards_in_current_slot += 1
                    
                    if cards_in_current_slot >= 2:
                        current_slot += 1
                        cards_in_current_slot = 0
            
            self.update_opponent_current_round_display()
    
    def handle_special_action_request(self, data):
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
    
    def on_special_action(self, action_type):
        """处理特殊操作点击"""
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
            print(f"Sent: {message}")
    
    def render_cards(self):
        """渲染卡牌"""
        # 清除现有卡牌
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.cards:
            no_cards_label = QLabel("暂无卡牌")
            no_cards_label.setAlignment(Qt.AlignCenter)
            no_cards_label.setStyleSheet("color: #666; padding: 20px;")
            self.cards_grid.addWidget(no_cards_label, 0, 0)
            return
        
        # 添加卡牌
        row, col = 0, 0
        max_cols = 6
        
        for i, card in enumerate(self.cards):
            unique_id = f"{card.name}_{i}"
            
            # 初始化使用状态
            if unique_id not in self.card_usage_map:
                self.card_usage_map[unique_id] = CardUsage(card=card)
            
            usage = self.card_usage_map[unique_id]
            
            # 创建卡牌控件
            card_widget = CardWidget(card, i)
            card_widget.is_used = usage.used
            
            # 设置鼠标事件
            card_widget.mousePressEvent = lambda event, widget=card_widget, idx=i, uid=unique_id: self.on_card_click(event, widget, idx, uid)
            
            self.cards_grid.addWidget(card_widget, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
    
    def on_card_click(self, event, widget, index, unique_id):
        """处理卡牌点击"""
        if event.button() == Qt.LeftButton:
            # 左键：选择卡牌
            self.selected_card = {
                'card': self.card_usage_map[unique_id].card,
                'index': index,
                'unique_id': unique_id
            }
        elif event.button() == Qt.RightButton:
            # 右键：显示详情
            self.show_card_detail(self.card_usage_map[unique_id].card)
    
    def add_card_to_slot(self, slot_index, card_data):
        """添加卡牌到栏位"""
        unique_id = card_data['unique_id']
        
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
        card_in_slot = Card(
            name=card_data['card'].name,
            HP=card_data['card'].HP,
            ATK=card_data['card'].ATK,
            property=card_data['card'].property,
            race=card_data['card'].race,
            cost=card_data['card'].cost,
            card_id=card_data['card'].card_id
        )
        
        self.current_round_slots[slot_index].append({
            'card': card_in_slot,
            'unique_id': unique_id,
            'slot_index': slot_index
        })
        
        # 更新使用状态
        usage.used = True
        usage.slot_index = slot_index
        
        # 发送更新给对手
        self.send_card_placement_update(slot_index, card_data['card'], 'add')
        
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
                    
                    # 更新使用状态
                    if removed_card['unique_id'] in self.card_usage_map:
                        usage = self.card_usage_map[removed_card['unique_id']]
                        usage.used = False
                        usage.slot_index = -1
                    
                    # 发送更新
                    self.send_card_placement_update(slot_index, removed_card['card'], 'remove')
                    break
        else:
            # 移除整个栏位的所有卡牌
            removed_cards = self.current_round_slots[slot_index].copy()
            self.current_round_slots[slot_index] = []
            
            # 更新使用状态
            for card_data in removed_cards:
                if card_data['unique_id'] in self.card_usage_map:
                    usage = self.card_usage_map[card_data['unique_id']]
                    usage.used = False
                    usage.slot_index = -1
        
        self.update_current_round_display()
        self.render_cards()
    
    def update_current_round_display(self):
        """更新当前回合显示"""
        for i, slot in enumerate(self.slots):
            # 清除现有内容
            while slot.layout() and slot.layout().count():
                item = slot.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # 创建新的布局
            layout = QVBoxLayout(slot)
            layout.setAlignment(Qt.AlignTop)
            
            cards = self.current_round_slots[i]
            
            if not cards:
                empty_label = QLabel("拖放卡牌到这里")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("color: #adb5bd; font-style: italic; padding: 20px;")
                layout.addWidget(empty_label)
            else:
                for card_data in cards:
                    card_widget = CardWidget(card_data['card'], 0)
                    card_widget.is_slot_card = True
                    card_widget.setFixedSize(170, 220)
                    
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
                    
                    # 添加卡牌和按钮
                    container_layout.addWidget(card_widget)
                    container_layout.addWidget(remove_btn, 0, Qt.AlignRight)
                    
                    layout.addWidget(container)
            
            slot.setLayout(layout)
        
        # 启用结束回合按钮
        self.play_btn.setEnabled(any(self.current_round_slots))
    
    def update_opponent_current_round_display(self):
        """更新对手当前回合显示"""
        for i, slot in enumerate(self.opponent_slots):
            # 清除现有内容
            while slot.layout() and slot.layout().count():
                item = slot.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # 创建新的布局
            layout = QVBoxLayout(slot)
            layout.setAlignment(Qt.AlignTop)
            
            cards = self.opponent_current_round_slots[i]
            
            if not cards:
                empty_label = QLabel("等待对方出牌")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("color: #adb5bd; font-style: italic; padding: 20px;")
                layout.addWidget(empty_label)
            else:
                for card in cards:
                    card_widget = CardWidget(card, 0)
                    card_widget.is_slot_card = True
                    card_widget.setFixedSize(170, 220)
                    card_widget.setStyleSheet("opacity: 0.9;")
                    
                    layout.addWidget(card_widget)
            
            slot.setLayout(layout)
    
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
    
    def play_current_round_cards(self):
        """结束当前回合"""
        if not self.connected:
            self.add_to_log("❌ 连接失败")
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
        
        if not all_cards:
            self.add_to_log("已结束，没有出牌")
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
        
        self.update_current_round_display()
        self.render_cards()
    
    def send_card_placement_update(self, slot_index, card, action):
        """发送卡牌放置更新"""
        if self.connected and self.websocket:
            update_msg = {
                'type': 'card_placement_update',
                'player_id': self.player_id,
                'slot_index': slot_index,
                'card': {
                    'name': card.name,
                    'HP': card.HP,
                    'ATK': card.ATK,
                    'property': card.property,
                    'race': card.race,
                    'cost': card.cost,
                    'card_id': card.card_id
                },
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
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                background-color: #007bff;
                color: white;
                padding: 15px;
                border-radius: 5px 5px 0 0;
            }
        """)
        layout.addWidget(title_label)
        
        # 详细信息
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        
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
        if card.cost:
            cost_items = []
            for cost_item in card.cost:
                if isinstance(cost_item, dict):
                    cost_items.append(f"{cost_item.get('resource', '')}: {cost_item.get('amount', '')}")
                else:
                    cost_items.append(str(cost_item))
            cost_text = ", ".join(cost_items)
        
        cost_widget = self.create_detail_row("费用", cost_text)
        detail_layout.addWidget(cost_widget)
        
        layout.addWidget(detail_widget)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec_()
    
    def create_detail_row(self, label, value):
        """创建详情行"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
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
    
    def update_status(self, message, status_type):
        """更新状态显示"""
        self.status_label.setText(message)
        
        if status_type == 'success':
            style = "background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb;"
        elif status_type == 'error':
            style = "background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;"
        else:  # info
            style = "background-color: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb;"
        
        self.status_label.setStyleSheet(f"QLabel {{ padding: 10px; border-radius: 5px; {style} }}")
    
    def add_to_log(self, message):
        """添加日志"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.log_text.append(f"[{timestamp}] {message}")
    
    def handle_reconnect_error(self, error_msg):
        """处理重连错误"""
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            delay = min(1000 * self.reconnect_attempts, 10000) / 1000
            
            self.update_status(
                f"🔄 重新连接中... (尝试 {self.reconnect_attempts}/{self.max_reconnect_attempts})",
                "info"
            )
            
            QTimer.singleShot(int(delay * 1000), self.connect_websocket)
        else:
            self.update_status("❌ 连接失败，请检查服务器状态和IP地址", "error")
    
    def update_connection(self):
        """更新连接"""
        self.server_ip = self.ip_input.text()
        self.reconnect_attempts = 0
        self.connect_websocket()

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle("Fusion")
    
    # 创建游戏客户端
    client = GameClient()
    client.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()