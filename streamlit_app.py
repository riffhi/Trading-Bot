

#!/usr/bin/env python3
"""
Enhanced Trading Bot Streamlit App
Author: Trading Bot Implementation
Description: Streamlit web interface for the enhanced trading bot
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

# Import the trading bot classes from the original file
import sys
import logging
import hmac
import hashlib
import urllib.parse
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
load_dotenv()
from trading_bot import EnhancedTradingBot, TradingBotLogger

# Set up the logger
logger = TradingBotLogger().get_logger()

# Import or define the trading bot classes (simplified for Streamlit)
class RequestsAPIClient:
    """Direct HTTP client for Binance API using requests"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, timeout: int = 10):
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.time_offset = 0
        
        if testnet:
            self.base_url = "https://testnet.binancefuture.com"
            self.fapi_url = "https://testnet.binancefuture.com/fapi/v1"
        else:
            self.base_url = "https://fapi.binance.com"
            self.fapi_url = "https://fapi.binance.com/fapi/v1"
        
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        self.session.headers.update({
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        })
        
        self._sync_time()
    
    def _sync_time(self):
        """Synchronize time with Binance server"""
        try:
            server_time_response = self.get_server_time()
            server_time = server_time_response['serverTime']
            local_time = int(time.time() * 1000)
            self.time_offset = server_time - local_time
        except Exception as e:
            st.warning(f"Could not sync time: {e}")
            self.time_offset = 0
    
    def _get_timestamp(self) -> int:
        """Get current timestamp synchronized with server"""
        local_time = int(time.time() * 1000)
        synchronized_time = local_time + self.time_offset - 1000
        return synchronized_time
    
    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for authenticated requests"""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """Make HTTP request to Binance API"""
        if params is None:
            params = {}
        
        url = f"{self.fapi_url}/{endpoint}"
        
        if signed:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    params['timestamp'] = self._get_timestamp()
                    query_string = urllib.parse.urlencode(params)
                    params['signature'] = self._generate_signature(query_string)
                    
                    if method.upper() == 'GET':
                        response = self.session.get(url, params=params, timeout=self.timeout)
                    elif method.upper() == 'POST':
                        response = self.session.post(url, data=params, timeout=self.timeout)
                    elif method.upper() == 'DELETE':
                        response = self.session.delete(url, params=params, timeout=self.timeout)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")
                    
                    response.raise_for_status()
                    
                    if not response.content:
                        return {}
                    
                    return response.json()
                    
                except requests.exceptions.RequestException as e:
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_code = error_data.get('code')
                            
                            if error_code == -1021:  # Timestamp error
                                self._sync_time()
                                if attempt < max_retries - 1:
                                    time.sleep(0.5)
                                    continue
                            
                            raise Exception(f"API Error {error_code}: {error_data.get('msg', str(e))}")
                        except json.JSONDecodeError:
                            pass
                    
                    if attempt == max_retries - 1:
                        raise Exception(f"Request failed after {max_retries} attempts: {str(e)}")
        else:
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url, params=params, timeout=self.timeout)
                elif method.upper() == 'POST':
                    response = self.session.post(url, data=params, timeout=self.timeout)
                elif method.upper() == 'DELETE':
                    response = self.session.delete(url, params=params, timeout=self.timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                
                if not response.content:
                    return {}
                
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        raise Exception(f"API Error {error_data.get('code', 'Unknown')}: {error_data.get('msg', str(e))}")
                    except:
                        pass
                raise Exception(f"Request failed: {str(e)}")
    
    def get_server_time(self) -> Dict:
        return self._make_request('GET', 'time')
    
    def get_exchange_info(self) -> Dict:
        return self._make_request('GET', 'exchangeInfo')
    
    def get_balance(self) -> List[Dict]:
        return self._make_request('GET', 'balance', signed=True)
    
    def get_position_info(self, symbol: str = None) -> List[Dict]:
        params = {}
        if symbol:
            params['symbol'] = symbol.upper()
        return self._make_request('GET', 'positionRisk', params, signed=True)
    
    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        params = {}
        if symbol:
            params['symbol'] = symbol.upper()
        return self._make_request('GET', 'openOrders', params, signed=True)
    
    def get_ticker_price(self, symbol: str) -> Dict:
        params = {'symbol': symbol.upper()}
        return self._make_request('GET', 'ticker/price', params)
    
    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[List]:
        params = {
            'symbol': symbol.upper(),
            'interval': interval,
            'limit': limit
        }
        return self._make_request('GET', 'klines', params)
    
    def place_order(self, symbol: str, side: str, order_type: str, **kwargs) -> Dict:
        params = {
            'symbol': symbol.upper(),
            'side': side.upper(),
            'type': order_type.upper()
        }
        
        if 'quantity' in kwargs:
            params['quantity'] = str(kwargs['quantity'])
        
        if 'price' in kwargs:
            params['price'] = str(kwargs['price'])
        
        if 'timeInForce' in kwargs:
            params['timeInForce'] = kwargs['timeInForce']
        elif order_type.upper() == 'LIMIT':
            params['timeInForce'] = 'GTC'
        
        for key, value in kwargs.items():
            if key not in ['quantity', 'price', 'timeInForce']:
                params[key] = str(value)
        
        return self._make_request('POST', 'order', params, signed=True)
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._make_request('DELETE', 'order', params, signed=True)
    
    def get_order(self, symbol: str, order_id: int) -> Dict:
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._make_request('GET', 'order', params, signed=True)

class EnhancedTradingBot:
    """Enhanced trading bot with Streamlit integration"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.testnet = testnet
        self.requests_client = RequestsAPIClient(api_key, api_secret, testnet)
        self._test_connection()
    
    def _test_connection(self):
        """Test API connection"""
        try:
            server_time = self.requests_client.get_server_time()
            return True
        except Exception as e:
            st.error(f"Connection test failed: {e}")
            return False
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        try:
            balance_info = self.requests_client.get_balance()
            positions_info = self.requests_client.get_position_info()
            
            usdt_balance = 0.0
            for balance in balance_info:
                if balance.get('asset') == 'USDT':
                    usdt_balance = float(balance.get('balance', 0))
                    break
            
            total_unrealized_pnl = sum(
                float(pos.get('unRealizedProfit', 0)) 
                for pos in positions_info 
                if float(pos.get('positionAmt', 0)) != 0
            )
            
            return {
                'totalWalletBalance': str(usdt_balance),
                'availableBalance': str(usdt_balance),
                'totalUnrealizedProfit': str(total_unrealized_pnl),
                'positions': positions_info,
                'assets': balance_info,
                'status': 'OK'
            }
            
        except Exception as e:
            return {
                'totalWalletBalance': '0.0',
                'availableBalance': '0.0',
                'totalUnrealizedProfit': '0.0',
                'positions': [],
                'assets': [],
                'status': 'Error',
                'error': True,
                'error_message': str(e)
            }
    
    def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        try:
            ticker = self.requests_client.get_ticker_price(symbol)
            return float(ticker['price'])
        except Exception as e:
            st.error(f"Error getting price for {symbol}: {e}")
            raise
    
    def get_klines_data(self, symbol: str, interval: str = '1h', limit: int = 100) -> pd.DataFrame:
        """Get candlestick data"""
        try:
            klines = self.requests_client.get_klines(symbol, interval, limit)
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            
            return df
        except Exception as e:
            st.error(f"Error getting klines data: {e}")
            return pd.DataFrame()
    
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict[str, Any]:
        """Place a market order"""
        try:
            order = self.requests_client.place_order(
                symbol=symbol,
                side=side,
                order_type='MARKET',
                quantity=quantity
            )
            return order
        except Exception as e:
            st.error(f"Error placing market order: {e}")
            raise
    
    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict[str, Any]:
        """Place a limit order"""
        try:
            order = self.requests_client.place_order(
                symbol=symbol,
                side=side,
                order_type='LIMIT',
                quantity=quantity,
                price=price,
                timeInForce='GTC'
            )
            return order
        except Exception as e:
            st.error(f"Error placing limit order: {e}")
            raise
    
    def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get open orders"""
        try:
            return self.requests_client.get_open_orders(symbol)
        except Exception as e:
            st.error(f"Error getting open orders: {e}")
            return []
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an order"""
        try:
            return self.requests_client.cancel_order(symbol, order_id)
        except Exception as e:
            st.error(f"Error cancelling order: {e}")
            raise

# Streamlit App Configuration
st.set_page_config(
    page_title="Enhanced Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    .success-message {
        background-color: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #c3e6cb;
    }
    .error-message {
        background-color: #f8d7da;
        color: #721c24;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #f5c6cb;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'bot' not in st.session_state:
    st.session_state.bot = None
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'account_info' not in st.session_state:
    st.session_state.account_info = None

def authenticate():
    """Handle authentication"""
    st.sidebar.header("🔐 Authentication")

    if not st.session_state.authenticated:
        with st.sidebar.form("auth_form"):
            api_key = st.text_input("API Key", type="password", value=st.session_state.get('temp_api_key', ''))
            api_secret = st.text_input("API Secret", type="password", value=st.session_state.get('temp_api_secret', ''))
            testnet = st.checkbox("Use Testnet", value=True)

            if st.form_submit_button("Connect"):
                if api_key and api_secret:
                    try:
                        st.session_state.temp_api_key = api_key
                        st.session_state.temp_api_secret = api_secret

                        with st.spinner("Connecting to Binance..."):
                            logger.info("Attempting connection to Binance...")
                            st.session_state.bot = EnhancedTradingBot(api_key, api_secret, testnet)
                            st.session_state.authenticated = True
                            logger.info("Successfully authenticated.")
                            del st.session_state.temp_api_key
                            del st.session_state.temp_api_secret
                            st.success("✅ Connected successfully!")
                            st.rerun()
                    except Exception as e:
                        logger.error(f"Authentication failed: {e}")
                        st.error(f"❌ Connection failed: {e}")
                else:
                    st.error("Please enter both API Key and API Secret")

    if st.session_state.authenticated:
        if st.sidebar.button("Disconnect"):
            logger.info("User disconnected from Binance.")
            st.session_state.bot = None
            st.session_state.authenticated = False
            st.session_state.account_info = None
            st.rerun()


# Main App
def main():
    """Main Streamlit application"""
    
    # Header
    st.markdown('<h1 class="main-header">📈 Enhanced Trading Bot</h1>', unsafe_allow_html=True)
    
    # Authentication
    authenticate()
    
    if not st.session_state.authenticated:
        st.info("👈 Please authenticate using the sidebar to get started.")
        
        # Show demo information
        st.markdown("## 🚀 Features")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            **📊 Account Management**
            - Real-time balance monitoring
            - Position tracking
            - PnL calculations
            """)
        
        with col2:
            st.markdown("""
            **📈 Trading Operations**
            - Market & Limit orders
            - Order management
            - Real-time price data
            """)
        
        with col3:
            st.markdown("""
            **📉 Analytics**
            - Price charts
            - Trading history
            - Performance metrics
            """)
        
        return
    
    # Main Dashboard
    bot = st.session_state.bot
    
    # Navigation Tabs on Top
    tabs = st.tabs(["📊 Dashboard", "💹 Trading", "📋 Orders", "📈 Analytics", "⚙️ Settings"])

    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto Refresh (30s)", value=False)
    if auto_refresh:
        time.sleep(30)
        st.rerun()
    
    # Page routing
    with tabs[0]:
        show_dashboard(bot)
    with tabs[1]:
        show_trading(bot)
    with tabs[2]:
        show_orders(bot)
    with tabs[3]:
        show_analytics(bot)
    with tabs[4]:
        show_settings(bot)


def show_dashboard(bot):
    """Show dashboard page"""
    st.header("📊 Dashboard")
    
    # Get account info
    try:
        with st.spinner("Loading account information..."):
            account_info = bot.get_account_info()
            st.session_state.account_info = account_info
    except Exception as e:
        st.error(f"Error loading account info: {e}")
        return
    
    # Account Summary
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_balance = float(account_info.get('totalWalletBalance', 0))
        st.metric("Total Balance", f"${total_balance:,.2f}", "USDT")
    
    with col2:
        available_balance = float(account_info.get('availableBalance', 0))
        st.metric("Available Balance", f"${available_balance:,.2f}", "USDT")
    
    with col3:
        unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0))
        delta_color = "normal" if unrealized_pnl >= 0 else "inverse"
        st.metric("Unrealized PnL", f"${unrealized_pnl:,.2f}", delta_color=delta_color)
    
    with col4:
        positions = account_info.get('positions', [])
        active_positions = len([p for p in positions if float(p.get('positionAmt', 0)) != 0])
        st.metric("Active Positions", active_positions)
    

    # Active Positions
    st.subheader("🎯 Active Positions")
    active_positions_data = []
    
    for position in positions:
        if float(position.get('positionAmt', 0)) != 0:
            active_positions_data.append({
                'Symbol': position.get('symbol', ''),
                'Size': float(position.get('positionAmt', 0)),
                'Entry Price': float(position.get('entryPrice', 0)),
                'Mark Price': float(position.get('markPrice', 0)),
                'PnL': float(position.get('unRealizedProfit', 0)),
                'ROE %': float(position.get('percentage', 0))
            })
    
    if active_positions_data:
        df = pd.DataFrame(active_positions_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No active positions")
    
    # Recent Activity
    st.subheader("📋 Recent Orders")
    try:
        open_orders = bot.get_open_orders()
        if open_orders:
            orders_data = []
            for order in open_orders[:10]:  # Show last 10 orders
                orders_data.append({
                    'Time': datetime.fromtimestamp(order.get('time', 0) / 1000).strftime('%Y-%m-%d %H:%M'),
                    'Symbol': order.get('symbol', ''),
                    'Side': order.get('side', ''),
                    'Type': order.get('type', ''),
                    'Quantity': float(order.get('origQty', 0)),
                    'Price': float(order.get('price', 0)),
                    'Status': order.get('status', '')
                })
            
            df = pd.DataFrame(orders_data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No recent orders")
    except Exception as e:
        st.error(f"Error loading orders: {e}")

def show_trading(bot):
    """Show trading page"""
    st.header("💹 Trading")
    
    # Symbol selection
    col1, col2 = st.columns([1, 1])
    
    with col1:
        symbol = st.text_input("Symbol", value="BTCUSDT", placeholder="e.g., BTCUSDT")
        
    with col2:
        if st.button("Get Current Price"):
            try:
                price = bot.get_current_price(symbol)
                st.success(f"Current price of {symbol}: ${price:,.2f}")
            except Exception as e:
                st.error(f"Error getting price: {e}")
    
    # Trading forms
    tab1, tab2 = st.tabs(["Market Order", "Limit Order"])
    
    with tab1:
        st.subheader("🎯 Market Order")
        with st.form("market_order_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                side = st.selectbox("Side", ["BUY", "SELL"])
                
            with col2:
                quantity = st.number_input("Quantity", min_value=0.001, step=0.001)
            
            if st.form_submit_button("Place Market Order", type="primary"):
                if quantity > 0:
                    try:
                        with st.spinner("Placing order..."):
                            order = bot.place_market_order(symbol, side, quantity)
                            st.success(f"✅ Market order placed successfully!")
                            st.json(order)
                    except Exception as e:
                        st.error(f"❌ Error placing order: {e}")
                else:
                    st.error("Please enter a valid quantity")
    
    with tab2:
        st.subheader("📊 Limit Order")
        with st.form("limit_order_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                side = st.selectbox("Side", ["BUY", "SELL"], key="limit_side")
                quantity = st.number_input("Quantity", min_value=0.001, step=0.001, key="limit_quantity")
                
            with col2:
                price = st.number_input("Price", min_value=0.01, step=0.01)
            
            if st.form_submit_button("Place Limit Order", type="primary"):
                if quantity > 0 and price > 0:
                    try:
                        with st.spinner("Placing order..."):
                            order = bot.place_limit_order(symbol, side, quantity, price)
                            st.success(f"✅ Limit order placed successfully!")
                            st.json(order)
                    except Exception as e:
                        st.error(f"❌ Error placing order: {e}")
                else:
                    st.error("Please enter valid quantity and price")

def show_orders(bot):
    """Show orders page"""
    st.header("📋 Orders Management")
    
    # Open Orders
    st.subheader("🔓 Open Orders")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        filter_symbol = st.text_input("Filter by Symbol (optional)", placeholder="e.g., BTCUSDT")
    
    with col2:
        if st.button("Refresh Orders"):
            st.rerun()
    
    try:
        with st.spinner("Loading open orders..."):
            open_orders = bot.get_open_orders(filter_symbol if filter_symbol else None)
        
        if open_orders:
            orders_data = []
            for order in open_orders:
                orders_data.append({
                    'Order ID': order.get('orderId', ''),
                    'Symbol': order.get('symbol', ''),
                    'Side': order.get('side', ''),
                    'Type': order.get('type', ''),
                    'Quantity': float(order.get('origQty', 0)),
                    'Filled': float(order.get('executedQty', 0)),
                    'Price': float(order.get('price', 0)),
                    'Status': order.get('status', ''),
                    'Time': datetime.fromtimestamp(order.get('time', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S')
                })
            
            df = pd.DataFrame(orders_data)
            
            # Display orders with selection
            selected_indices = st.dataframe(
                df, 
                use_container_width=True,
                selection_mode="multi-row",
                on_select="rerun"
            )
            
            # Cancel order functionality
            if st.button("Cancel Selected Orders", type="secondary"):
                if hasattr(selected_indices, 'selection') and selected_indices.selection['rows']:
                    for idx in selected_indices.selection['rows']:
                        try:
                            order_id = int(df.iloc[idx]['Order ID'])
                            symbol = df.iloc[idx]['Symbol']
                            bot.cancel_order(symbol, order_id)
                            st.success(f"✅ Cancelled order {order_id}")
                        except Exception as e:
                            st.error(f"❌ Error cancelling order {order_id}: {e}")
                    st.rerun()
                else:
                    st.warning("Please select orders to cancel")
        else:
            st.info("No open orders found")
            
    except Exception as e:
        st.error(f"Error loading orders: {e}")

def show_analytics(bot):
    """Show analytics page"""
    st.header("📈 Analytics")
    
    # Symbol and timeframe selection
    col1, col2, col3 = st.columns(3)
    
    with col1:
        symbol = st.selectbox("Symbol", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"])
    
    with col2:
        interval = st.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h", "1d"])
    
    with col3:
        limit = st.selectbox("Candles", [50, 100, 200, 500])
    
    # Get chart data
    try:
        with st.spinner("Loading chart data..."):
            df = bot.get_klines_data(symbol, interval, limit)
        
        if not df.empty:
            # Candlestick chart
            fig = go.Figure(data=go.Candlestick(
                x=df['timestamp'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name=symbol
            ))
            
            fig.update_layout(
                title=f"{symbol} Candlestick Chart ({interval})",
                xaxis_title="Time",
                yaxis_title="Price (USDT)",
                height=600
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Volume chart
            fig_volume = go.Figure(data=go.Bar(
                x=df['timestamp'],
                y=df['volume'],
                name="Volume"
            ))
            
            fig_volume.update_layout(
                title=f"{symbol} Volume",
                xaxis_title="Time",
                yaxis_title="Volume",
                height=300
            )
            
            st.plotly_chart(fig_volume, use_container_width=True)
            
            # Price statistics
            st.subheader("📊 Price Statistics")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Current Price", f"${df['close'].iloc[-1]:,.2f}")
            
            with col2:
                price_change = df['close'].iloc[-1] - df['close'].iloc[-2]
                price_change_pct = (price_change / df['close'].iloc[-2]) * 100
                st.metric("24h Change", f"${price_change:,.2f}", f"{price_change_pct:+.2f}%")
            
            with col3:
                st.metric("24h High", f"${df['high'].max():,.2f}")
            
            with col4:
                st.metric("24h Low", f"${df['low'].min():,.2f}")
            
            # Technical indicators
            st.subheader("📉 Technical Analysis")
            
            # Simple Moving Averages
            df['SMA_20'] = df['close'].rolling(window=20).mean()
            df['SMA_50'] = df['close'].rolling(window=50).mean()
            
            # RSI calculation
            def calculate_rsi(prices, period=14):
                delta = prices.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                return rsi
            
            df['RSI'] = calculate_rsi(df['close'])
            
            # Display technical indicators
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Moving Averages**")
                st.write(f"SMA 20: ${df['SMA_20'].iloc[-1]:,.2f}")
                st.write(f"SMA 50: ${df['SMA_50'].iloc[-1]:,.2f}")
                
                if df['SMA_20'].iloc[-1] > df['SMA_50'].iloc[-1]:
                    st.success("🟢 Bullish Signal (SMA20 > SMA50)")
                else:
                    st.error("🔴 Bearish Signal (SMA20 < SMA50)")
            
            with col2:
                current_rsi = df['RSI'].iloc[-1]
                st.write(f"**RSI (14): {current_rsi:.2f}**")
                
                if current_rsi > 70:
                    st.warning("⚠️ Overbought (RSI > 70)")
                elif current_rsi < 30:
                    st.warning("⚠️ Oversold (RSI < 30)")
                else:
                    st.info("ℹ️ Neutral (30 < RSI < 70)")
            
            # Raw data
            with st.expander("📋 Raw Data"):
                st.dataframe(df.tail(20), use_container_width=True)
                
        else:
            st.error("No data available for the selected symbol and timeframe")
            
    except Exception as e:
        st.error(f"Error loading analytics: {e}")

def show_settings(bot):
    """Show settings page"""
    st.header("⚙️ Settings")
    
    # Trading Settings
    st.subheader("📊 Trading Preferences")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Default Settings**")
        default_quantity = st.number_input("Default Quantity", min_value=0.001, value=0.01, step=0.001)
        default_symbols = st.multiselect(
            "Favorite Symbols", 
            ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "DOTUSDT", "LINKUSDT"],
            default=["BTCUSDT", "ETHUSDT"]
        )
    
    with col2:
        st.write("**Risk Management**")
        max_position_size = st.number_input("Max Position Size (%)", min_value=1, max_value=100, value=10)
        stop_loss_pct = st.number_input("Default Stop Loss (%)", min_value=0.1, max_value=50.0, value=2.0, step=0.1)
        take_profit_pct = st.number_input("Default Take Profit (%)", min_value=0.1, max_value=100.0, value=5.0, step=0.1)
    
    # Display Settings
    st.subheader("🎨 Display Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        chart_theme = st.selectbox("Chart Theme", ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn"])
        refresh_interval = st.selectbox("Auto Refresh Interval", [10, 30, 60, 120, 300], index=1)
    
    with col2:
        show_notifications = st.checkbox("Show Notifications", value=True)
        sound_alerts = st.checkbox("Sound Alerts", value=False)
    
    # API Settings
    st.subheader("🔧 API Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Connection Status**")
        if st.session_state.get('authenticated', False):
            st.success("🟢 Connected")
            if st.session_state.bot.testnet:
                st.info("📡 Using Testnet")
            else:
                st.warning("🌐 Using Live Trading")
        else:
            st.error("🔴 Not Connected")
    
    with col2:
        st.write("**Actions**")
        if st.button("Test Connection"):
            try:
                server_time = bot.requests_client.get_server_time()
                st.success(f"✅ Connection successful! Server time: {datetime.fromtimestamp(server_time['serverTime']/1000)}")
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")
    
    # Save Settings
    if st.button("💾 Save Settings", type="primary"):
        settings = {
            'default_quantity': default_quantity,
            'default_symbols': default_symbols,
            'max_position_size': max_position_size,
            'stop_loss_pct': stop_loss_pct,
            'take_profit_pct': take_profit_pct,
            'chart_theme': chart_theme,
            'refresh_interval': refresh_interval,
            'show_notifications': show_notifications,
            'sound_alerts': sound_alerts
        }
        
        # In a real app, you'd save these to a file or database
        st.session_state.settings = settings
        st.success("✅ Settings saved successfully!")
    
    # Export/Import Settings
    st.subheader("📁 Backup & Restore")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📤 Export Settings"):
            if 'settings' in st.session_state:
                settings_json = json.dumps(st.session_state.settings, indent=2)
                st.download_button(
                    label="Download Settings",
                    data=settings_json,
                    file_name=f"trading_bot_settings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
            else:
                st.warning("No settings to export")
    
    with col2:
        uploaded_file = st.file_uploader("📥 Import Settings", type=['json'])
        if uploaded_file is not None:
            try:
                settings = json.load(uploaded_file)
                st.session_state.settings = settings
                st.success("✅ Settings imported successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error importing settings: {e}")
    
    # Advanced Settings
    with st.expander("🔬 Advanced Settings"):
        st.warning("⚠️ Advanced settings - modify with caution!")
        
        api_timeout = st.number_input("API Timeout (seconds)", min_value=5, max_value=60, value=10)
        max_retries = st.number_input("Max API Retries", min_value=1, max_value=10, value=3)
        
        if st.checkbox("Enable Debug Logging"):
            st.info("Debug logging will be enabled for troubleshooting")
        
        if st.button("🔄 Reset to Defaults"):
            # Clear all settings
            if 'settings' in st.session_state:
                del st.session_state.settings
            st.success("✅ Settings reset to defaults!")
            st.rerun()

# Error handling and logging
def setup_logging():
    """Setup logging for the application"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )

# Footer
def show_footer():
    """Show application footer"""
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; padding: 1rem;'>
            <p>Enhanced Trading Bot v1.0 | Built with Streamlit</p>
            <p><small>⚠️ This is for educational purposes only. Trade at your own risk.</small></p>
        </div>
        """, 
        unsafe_allow_html=True
    )

# Run the application
if __name__ == "__main__":
    setup_logging()
    
    try:
        main()
        show_footer()
    except Exception as e:
        st.error(f"Application error: {e}")
        st.info("Please refresh the page and try again.")
        
    # Add some spacing at the bottom
    st.markdown("<br><br>", unsafe_allow_html=True)