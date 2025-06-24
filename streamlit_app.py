#!/usr/bin/env python3
"""
Streamlit Frontend for Binance Futures Trading Bot
Author: Trading Bot Implementation
Description: Web-based interface for the trading bot with real-time data and interactive controls
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time
import json
import os
from typing import Dict, Any, List, Optional
import asyncio
from decimal import Decimal, ROUND_DOWN

# Import the trading bot (assuming it's in the same directory)
try:
    from trading_bot import BasicBot, TradingBotLogger
    from binance.exceptions import BinanceAPIException, BinanceOrderException
except ImportError:
    st.error("Trading bot module not found. Make sure 'paste.py' is in the same directory.")
    st.stop()

# Page configuration
st.set_page_config(
    page_title="Binance Futures Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .success-message {
        color: #28a745;
        font-weight: bold;
    }
    .error-message {
        color: #dc3545;
        font-weight: bold;
    }
    .warning-message {
        color: #ffc107;
        font-weight: bold;
    }
    .order-card {
        border: 1px solid #dee2e6;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 0.5rem 0;
        background-color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

class TradingBotApp:
    """Streamlit Trading Bot Application"""
    
    def __init__(self):
        self.initialize_session_state()
        self.logger = TradingBotLogger().get_logger()
    
    def initialize_session_state(self):
        """Initialize Streamlit session state variables"""
        if 'bot' not in st.session_state:
            st.session_state.bot = None
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        if 'api_key' not in st.session_state:
            st.session_state.api_key = ""
        if 'api_secret' not in st.session_state:
            st.session_state.api_secret = ""
        if 'auto_refresh' not in st.session_state:
            st.session_state.auto_refresh = False
        if 'selected_symbol' not in st.session_state:
            st.session_state.selected_symbol = "BTCUSDT"
        if 'order_history' not in st.session_state:
            st.session_state.order_history = []
    
    def authenticate(self):
        """Handle API authentication"""
        st.sidebar.header("🔐 API Configuration")
        
        if not st.session_state.authenticated:
            with st.sidebar.form("api_form"):
                api_key = st.text_input(
                    "Binance API Key",
                    type="password",
                    value=st.session_state.api_key,
                    help="Enter your Binance API Key"
                )
                api_secret = st.text_input(
                    "Binance API Secret",
                    type="password",
                    value=st.session_state.api_secret,
                    help="Enter your Binance API Secret"
                )
                testnet = st.checkbox("Use Testnet", value=True, help="Use Binance Testnet for safe testing")
                
                if st.form_submit_button("Connect", type="primary"):
                    if api_key and api_secret:
                        try:
                            with st.spinner("Connecting to Binance..."):
                                bot = BasicBot(api_key, api_secret, testnet=testnet)
                                st.session_state.bot = bot
                                st.session_state.authenticated = True
                                st.session_state.api_key = api_key
                                st.session_state.api_secret = api_secret
                            st.success("✅ Connected successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Connection failed: {str(e)}")
                    else:
                        st.error("Please enter both API key and secret")
        else:
            st.sidebar.success("✅ Connected to Binance")
            if st.sidebar.button("Disconnect", type="secondary"):
                st.session_state.authenticated = False
                st.session_state.bot = None
                st.rerun()
    
    def main_dashboard(self):
        """Main dashboard with account info and controls"""
        if not st.session_state.authenticated:
            st.warning("Please authenticate with your API credentials in the sidebar.")
            return
        
        # Header
        st.markdown('<h1 class="main-header">📈 Binance Futures Trading Bot</h1>', unsafe_allow_html=True)
        
        # Account overview
        self.display_account_overview()
        
        # Main content tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Market Data", 
            "💼 Trading", 
            "📋 Orders", 
            "📈 Positions", 
            "📜 Logs"
        ])
        
        with tab1:
            self.market_data_tab()
        
        with tab2:
            self.trading_tab()
        
        with tab3:
            self.orders_tab()
        
        with tab4:
            self.positions_tab()
        
        with tab5:
            self.logs_tab()
    
    def display_account_overview(self):
        """Display account overview metrics"""
        try:
            account_info = st.session_state.bot.get_account_info()
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "💰 Total Balance",
                    f"${float(account_info.get('totalWalletBalance', 0)):,.2f}",
                    delta=None
                )
            
            with col2:
                st.metric(
                    "💵 Available Balance",
                    f"${float(account_info.get('availableBalance', 0)):,.2f}",
                    delta=None
                )
            
            with col3:
                unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0))
                st.metric(
                    "📊 Unrealized PnL",
                    f"${unrealized_pnl:,.2f}",
                    delta=f"{unrealized_pnl:+,.2f}",
                    delta_color="normal"
                )
            
            with col4:
                positions = account_info.get('positions', [])
                active_positions = len([p for p in positions if float(p.get('positionAmt', 0)) != 0])
                st.metric(
                    "🎯 Active Positions",
                    str(active_positions),
                    delta=None
                )
        
        except Exception as e:
            st.error(f"Error loading account info: {str(e)}")
    
    def market_data_tab(self):
        """Market data and price monitoring tab"""
        st.header("📊 Market Data")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Symbol selection
            symbol = st.selectbox(
                "Select Trading Pair",
                ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"],
                index=0,
                key="market_symbol"
            )
            st.session_state.selected_symbol = symbol
        
        with col2:
            # Auto refresh toggle
            auto_refresh = st.checkbox("Auto Refresh (10s)", value=st.session_state.auto_refresh)
            st.session_state.auto_refresh = auto_refresh
        
        # Current price display
        try:
            current_price = st.session_state.bot.get_current_price(symbol)
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    f"{symbol} Price",
                    f"${current_price:,.4f}",
                    delta=None
                )
            
            with col2:
                if st.button("🔄 Refresh Price", key="refresh_price"):
                    st.rerun()
        
        except Exception as e:
            st.error(f"Error getting price data: {str(e)}")
        
        # Auto refresh functionality
        if auto_refresh:
            time.sleep(10)
            st.rerun()
    
    def trading_tab(self):
        """Trading interface tab"""
        st.header("💼 Trading")
        
        # Order type selection
        order_type = st.selectbox(
            "Order Type",
            ["Market Order", "Limit Order", "Stop-Limit Order"],
            key="order_type"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Buy Orders")
            self.create_order_form("BUY", order_type)
        
        with col2:
            st.subheader("📉 Sell Orders")
            self.create_order_form("SELL", order_type)
    
    def create_order_form(self, side: str, order_type: str):
        """Create order form for buy/sell"""
        with st.form(f"{side.lower()}_order_form"):
            symbol = st.selectbox(
                "Symbol",
                ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"],
                key=f"{side.lower()}_symbol"
            )
            
            quantity = st.number_input(
                "Quantity",
                min_value=0.001,
                step=0.001,
                format="%.3f",
                key=f"{side.lower()}_quantity"
            )
            
            price = None
            stop_price = None
            
            if order_type != "Market Order":
                price = st.number_input(
                    "Price (USDT)",
                    min_value=0.01,
                    step=0.01,
                    format="%.2f",
                    key=f"{side.lower()}_price"
                )
            
            if order_type == "Stop-Limit Order":
                stop_price = st.number_input(
                    "Stop Price (USDT)",
                    min_value=0.01,
                    step=0.01,
                    format="%.2f",
                    key=f"{side.lower()}_stop_price"
                )
            
            color = "green" if side == "BUY" else "red"
            if st.form_submit_button(f"{side} {order_type}", type="primary"):
                self.place_order(symbol, side, order_type, quantity, price, stop_price)
    
    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, 
                   price: Optional[float] = None, stop_price: Optional[float] = None):
        """Place an order"""
        try:
            with st.spinner(f"Placing {side.lower()} {order_type.lower()}..."):
                if order_type == "Market Order":
                    order = st.session_state.bot.place_market_order(symbol, side, quantity)
                elif order_type == "Limit Order":
                    if not price:
                        st.error("Price is required for limit orders")
                        return
                    order = st.session_state.bot.place_limit_order(symbol, side, quantity, price)
                elif order_type == "Stop-Limit Order":
                    if not price or not stop_price:
                        st.error("Price and stop price are required for stop-limit orders")
                        return
                    order = st.session_state.bot.place_stop_limit_order(symbol, side, quantity, price, stop_price)
                
                # Add to order history
                order_record = {
                    'timestamp': datetime.now(),
                    'symbol': symbol,
                    'side': side,
                    'type': order_type,
                    'quantity': quantity,
                    'price': price,
                    'stop_price': stop_price,
                    'order_id': order.get('orderId'),
                    'status': order.get('status'),
                    'response': order
                }
                st.session_state.order_history.append(order_record)
                
                st.success(f"✅ {side} order placed successfully!")
                st.json(order)
        
        except Exception as e:
            st.error(f"❌ Error placing order: {str(e)}")
    
    def orders_tab(self):
        """Orders management tab"""
        st.header("📋 Order Management")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔍 Open Orders")
            if st.button("🔄 Refresh Open Orders"):
                st.rerun()
            
            try:
                open_orders = st.session_state.bot.get_open_orders()
                
                if open_orders:
                    for order in open_orders:
                        with st.container():
                            st.markdown(f"""
                            <div class="order-card">
                                <strong>Order ID:</strong> {order.get('orderId')}<br>
                                <strong>Symbol:</strong> {order.get('symbol')}<br>
                                <strong>Side:</strong> {order.get('side')}<br>
                                <strong>Type:</strong> {order.get('type')}<br>
                                <strong>Quantity:</strong> {order.get('origQty')}<br>
                                <strong>Price:</strong> {order.get('price')}<br>
                                <strong>Status:</strong> {order.get('status')}
                            </div>
                            """, unsafe_allow_html=True)
                            
                            if st.button(f"❌ Cancel", key=f"cancel_{order.get('orderId')}"):
                                self.cancel_order(order.get('symbol'), order.get('orderId'))
                else:
                    st.info("No open orders found")
            
            except Exception as e:
                st.error(f"Error loading open orders: {str(e)}")
        
        with col2:
            st.subheader("📊 Order Status Check")
            
            with st.form("order_status_form"):
                symbol = st.text_input("Symbol", value="BTCUSDT")
                order_id = st.number_input("Order ID", min_value=1, step=1)
                
                if st.form_submit_button("Check Status"):
                    self.check_order_status(symbol, int(order_id))
        
        # Order history
        st.subheader("📜 Recent Order History")
        if st.session_state.order_history:
            df = pd.DataFrame([
                {
                    'Time': record['timestamp'].strftime('%H:%M:%S'),
                    'Symbol': record['symbol'],
                    'Side': record['side'],
                    'Type': record['type'],
                    'Quantity': record['quantity'],
                    'Price': record['price'],
                    'Status': record['status']
                }
                for record in st.session_state.order_history[-10:]  # Last 10 orders
            ])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No order history available")
    
    def cancel_order(self, symbol: str, order_id: int):
        """Cancel an order"""
        try:
            with st.spinner("Cancelling order..."):
                result = st.session_state.bot.cancel_order(symbol, order_id)
                st.success(f"✅ Order {order_id} cancelled successfully!")
                st.rerun()
        except Exception as e:
            st.error(f"❌ Error cancelling order: {str(e)}")
    
    def check_order_status(self, symbol: str, order_id: int):
        """Check order status"""
        try:
            order = st.session_state.bot.get_order_status(symbol, order_id)
            
            st.subheader(f"Order {order_id} Status")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Symbol:** {order.get('symbol')}")
                st.write(f"**Side:** {order.get('side')}")
                st.write(f"**Type:** {order.get('type')}")
                st.write(f"**Status:** {order.get('status')}")
            
            with col2:
                st.write(f"**Original Qty:** {order.get('origQty')}")
                st.write(f"**Executed Qty:** {order.get('executedQty')}")
                st.write(f"**Price:** {order.get('price')}")
                st.write(f"**Average Price:** {order.get('avgPrice')}")
            
            if order.get('time'):
                order_time = datetime.fromtimestamp(order.get('time') / 1000)
                st.write(f"**Time:** {order_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        except Exception as e:
            st.error(f"Error checking order status: {str(e)}")
    
    def positions_tab(self):
        """Positions overview tab"""
        st.header("📈 Positions")
        
        try:
            account_info = st.session_state.bot.get_account_info()
            positions = account_info.get('positions', [])
            active_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
            
            if active_positions:
                for position in active_positions:
                    with st.container():
                        st.markdown(f"""
                        <div class="order-card">
                            <strong>Symbol:</strong> {position.get('symbol')}<br>
                            <strong>Position Size:</strong> {position.get('positionAmt')}<br>
                            <strong>Entry Price:</strong> {position.get('entryPrice')}<br>
                            <strong>Mark Price:</strong> {position.get('markPrice')}<br>
                            <strong>Unrealized PnL:</strong> {position.get('unrealizedProfit')}<br>
                            <strong>ROE:</strong> {float(position.get('percentage', 0)):.2f}%
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No active positions")
        
        except Exception as e:
            st.error(f"Error loading positions: {str(e)}")
    
    def logs_tab(self):
        """Logs and system information tab"""
        st.header("📜 System Logs")
        
        # Log files location
        logs_dir = os.path.abspath('logs')
        st.write(f"**Log Directory:** `{logs_dir}`")
        
        if os.path.exists(logs_dir):
            log_files = [f for f in os.listdir(logs_dir) if f.endswith('.log')]
            
            if log_files:
                selected_log = st.selectbox("Select Log File", sorted(log_files, reverse=True))
                
                if selected_log:
                    log_path = os.path.join(logs_dir, selected_log)
                    
                    try:
                        with open(log_path, 'r') as f:
                            log_content = f.read()
                        
                        st.text_area(
                            "Log Content",
                            value=log_content[-2000:],  # Last 2000 characters
                            height=400,
                            disabled=True
                        )
                        
                        if st.button("📥 Download Log File"):
                            st.download_button(
                                label="Download",
                                data=log_content,
                                file_name=selected_log,
                                mime="text/plain"
                            )
                    
                    except Exception as e:
                        st.error(f"Error reading log file: {str(e)}")
            else:
                st.info("No log files found")
        else:
            st.info("Logs directory does not exist yet")
        
        # Session information
        st.subheader("🔧 Session Information")
        st.write(f"**Authenticated:** {'Yes' if st.session_state.authenticated else 'No'}")
        st.write(f"**Selected Symbol:** {st.session_state.selected_symbol}")
        st.write(f"**Auto Refresh:** {'Enabled' if st.session_state.auto_refresh else 'Disabled'}")
        st.write(f"**Orders in History:** {len(st.session_state.order_history)}")
    
    def run(self):
        """Run the Streamlit application"""
        self.authenticate()
        self.main_dashboard()


def main():
    """Main function to run the Streamlit app"""
    app = TradingBotApp()
    app.run()


if __name__ == "__main__":
    main()