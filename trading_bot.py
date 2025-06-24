#!/usr/bin/env python3
"""
Enhanced Trading Bot for Binance Futures with Requests Integration
Author: Trading Bot Implementation
Description: Enhanced trading bot with direct HTTP requests and fallback mechanisms
"""

import os
import sys
import json
import logging
import argparse
import time
import hmac
import hashlib
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()


# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Setup logging
log_filename = datetime.now().strftime("logs/trading_bot_%Y%m%d_%H%M%S.log")
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("TradingBot")

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    from binance.enums import *
except ImportError:
    print("Warning: python-binance library not installed. Using requests-only mode.")
    Client = None
    BinanceAPIException = Exception
    BinanceOrderException = Exception

class RequestsAPIClient:
    """Direct HTTP client for Binance API using requests"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, timeout: int = 10):
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.time_offset = 0  # Add time offset tracking
        
        # Set base URLs
        if testnet:
            self.base_url = "https://testnet.binancefuture.com"
            self.fapi_url = "https://testnet.binancefuture.com/fapi/v1"
        else:
            self.base_url = "https://fapi.binance.com"
            self.fapi_url = "https://fapi.binance.com/fapi/v1"
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # Sync time on initialization
        self._sync_time()
    
    def _sync_time(self):
        """Synchronize time with Binance server"""
        try:
            server_time_response = self.get_server_time()
            server_time = server_time_response['serverTime']
            local_time = int(time.time() * 1000)
            
            # Calculate offset (server time - local time)
            self.time_offset = server_time - local_time
            print(f"Time synchronized. Server time: {server_time}, Local time: {local_time}, Offset: {self.time_offset}ms")
            
        except Exception as e:
            print(f"Warning: Could not sync time: {e}")
            self.time_offset = 0
    
    def _get_timestamp(self) -> int:
        """Get current timestamp synchronized with server"""
        local_time = int(time.time() * 1000)
        # Apply offset and add small buffer to ensure we're not ahead
        synchronized_time = local_time + self.time_offset - 1000  # Subtract 1 second buffer
        return synchronized_time
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """Make HTTP request to Binance API"""
        if params is None:
            params = {}
        
        url = f"{self.fapi_url}/{endpoint}"
        
        if signed:
            # Handle timestamp synchronization issues
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
                            
                            # Handle timestamp errors specifically
                            if error_code == -1021:  # Timestamp error
                                print(f"Timestamp error on attempt {attempt + 1}, resyncing time...")
                                self._sync_time()
                                if attempt < max_retries - 1:
                                    time.sleep(0.5)  # Brief pause before retry
                                    continue
                            
                            print(f"API Error: {error_data}")
                            raise Exception(f"API Error {error_code}: {error_data.get('msg', str(e))}")
                        except json.JSONDecodeError:
                            pass
                    
                    if attempt == max_retries - 1:
                        raise Exception(f"Request failed after {max_retries} attempts: {str(e)}")
        else:
            # Non-signed requests
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
                print(f"Request error: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        print(f"API Error: {error_data}")
                        raise Exception(f"API Error {error_data.get('code', 'Unknown')}: {error_data.get('msg', str(e))}")
                    except:
                        pass
                raise Exception(f"Request failed: {str(e)}")
     
    def ping(self) -> Dict:
        """Test connectivity"""
        return self._make_request('GET', 'ping')

    def get_server_time(self) -> Dict:
        """Get server time"""
        return self._make_request('GET', 'time')

    def get_exchange_info(self) -> Dict:
        """Get exchange trading rules and symbol information"""
        return self._make_request('GET', 'exchangeInfo')

    def get_account_info(self) -> Dict:
        """Get account information"""
        return self._make_request('GET', 'account', signed=True)

    def get_balance(self) -> List[Dict]:
        """Get account balance"""
        return self._make_request('GET', 'balance', signed=True)

    def get_position_info(self, symbol: str = None) -> List[Dict]:
        """Get position information"""
        params = {}
        if symbol:
            params['symbol'] = symbol.upper()
        return self._make_request('GET', 'positionRisk', params, signed=True)

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """Get open orders"""
        params = {}
        if symbol:
            params['symbol'] = symbol.upper()
        return self._make_request('GET', 'openOrders', params, signed=True)

    def get_ticker_price(self, symbol: str) -> Dict:
        """Get symbol price ticker"""
        params = {'symbol': symbol.upper()}
        return self._make_request('GET', 'ticker/price', params)

    def place_order(self, symbol: str, side: str, order_type: str, **kwargs) -> Dict:
        """Place a new order"""
        params = {
            'symbol': symbol.upper(),
            'side': side.upper(),
            'type': order_type.upper()
        }
        
        # Handle quantity parameter
        if 'quantity' in kwargs:
            params['quantity'] = str(kwargs['quantity'])
        
        # Handle price parameter for limit orders
        if 'price' in kwargs:
            params['price'] = str(kwargs['price'])
        
        # Handle timeInForce for limit orders
        if 'timeInForce' in kwargs:
            params['timeInForce'] = kwargs['timeInForce']
        elif order_type.upper() == 'LIMIT':
            params['timeInForce'] = 'GTC'  # Default to Good Till Cancelled
        
        # Add any other parameters
        for key, value in kwargs.items():
            if key not in ['quantity', 'price', 'timeInForce']:
                params[key] = str(value)
        
        return self._make_request('POST', 'order', params, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        """Cancel an order"""
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._make_request('DELETE', 'order', params, signed=True)

    def get_order(self, symbol: str, order_id: int) -> Dict:
        """Get order status"""
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._make_request('GET', 'order', params, signed=True)
    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for authenticated requests"""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

# Also update the TimestampSync class to work better with the RequestsAPIClient
class TimestampSync:
    """Handle timestamp synchronization with Binance servers"""
    
    def __init__(self):
        self.time_offset = 0
        self.last_sync = 0
        self.sync_interval = 300  # Sync every 5 minutes
    
    def sync_time(self, client):
        """Synchronize time with Binance server"""
        try:
            if hasattr(client, 'get_server_time'):
                # Using requests client
                server_time_response = client.get_server_time()
                server_time = server_time_response['serverTime']
            else:
                # Using python-binance client
                server_time_response = client.get_server_time()
                server_time = server_time_response['serverTime']
            
            # Get local time in milliseconds
            local_time = int(time.time() * 1000)
            
            # Calculate offset with safety buffer
            raw_offset = server_time - local_time
            # Add buffer to ensure we're slightly behind server time
            self.time_offset = raw_offset - 1000  # 1 second buffer
            self.last_sync = time.time()
            
            print(f"Time synchronized. Raw offset: {raw_offset}ms, Applied offset: {self.time_offset}ms")
            
            # Update client's time offset if it's the requests client
            if hasattr(client, 'time_offset'):
                client.time_offset = self.time_offset
            
            return True
            
        except Exception as e:
            print(f"Failed to sync time: {e}")
            return False
    
    def get_synchronized_timestamp(self):
        """Get current timestamp synchronized with Binance server"""
        current_time = int(time.time() * 1000)
        return current_time + self.time_offset
    
    def should_resync(self):
        """Check if time resync is needed"""
        return (time.time() - self.last_sync) > self.sync_interval

class TradingBotLogger:
    """Enhanced logging system for the trading bot"""
    
    def __init__(self, log_level=logging.INFO):
        self.logger = logging.getLogger('TradingBot')
        self.logger.setLevel(log_level)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # File handler with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_handler = logging.FileHandler(f'logs/trading_bot_{timestamp}.log')
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def get_logger(self):
        return self.logger

class EnhancedTradingBot:
    """Enhanced trading bot with requests integration and fallback mechanisms"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, use_requests_only: bool = False):
        """
        Initialize the enhanced trading bot
        
        Args:
            api_key: Binance API key  
            api_secret: Binance API secret
            testnet: Use testnet environment (default: True)
            use_requests_only: Use only requests client, not python-binance (default: False)
        """
        self.testnet = testnet
        self.use_requests_only = use_requests_only
        self.logger = TradingBotLogger().get_logger()
        self.time_sync = TimestampSync()
        
        # Initialize clients
        self.requests_client = RequestsAPIClient(api_key, api_secret, testnet)
        
        if Client and not use_requests_only:
            try:
                if testnet:
                    self.binance_client = Client(
                        api_key=api_key,
                        api_secret=api_secret,
                        testnet=True,
                        tld='com'
                    )
                else:
                    self.binance_client = Client(
                        api_key=api_key,
                        api_secret=api_secret,
                        testnet=False,
                        tld='com'
                    )
                self.logger.info("Both requests and python-binance clients initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize python-binance client: {e}")
                self.binance_client = None
                self.use_requests_only = True
        else:
            self.binance_client = None
            self.use_requests_only = True
            
        if self.use_requests_only:
            self.logger.info("Using requests-only mode")
        
        # Test connection
        self._test_connection()
    
    def _make_api_call(self, method_name: str, *args, **kwargs):
        """Make API call with fallback between clients"""
        if not self.use_requests_only and self.binance_client:
            try:
                # Try python-binance first
                method = getattr(self.binance_client, method_name, None)
                if method:
                    return method(*args, **kwargs)
            except Exception as e:
                self.logger.warning(f"python-binance method {method_name} failed: {e}")
                # Fall back to requests client
        
        # Use requests client
        return self._make_requests_call(method_name, *args, **kwargs)
    
    def _make_requests_call(self, method_name: str, *args, **kwargs):
        """Make API call using requests client"""
        method_mapping = {
            'get_server_time': 'get_server_time',
            'futures_exchange_info': 'get_exchange_info', 
            'futures_account_balance': 'get_balance',
            'futures_position_information': 'get_position_info',
            'futures_get_open_orders': 'get_open_orders',
            'futures_symbol_ticker': 'get_ticker_price',
            'futures_create_order': 'place_order',
            'futures_cancel_order': 'cancel_order',
            'futures_get_order': 'get_order'
        }
        
        requests_method = method_mapping.get(method_name)
        if not requests_method:
            raise NotImplementedError(f"Method {method_name} not implemented in requests client")
        
        method = getattr(self.requests_client, requests_method)
        return method(*args, **kwargs)
    
    def _test_connection(self):
        """Test API connection"""
        try:
            self.logger.info("Testing API connection...")
            
            # Test server time
            server_time = self.requests_client.get_server_time()
            self.logger.info(f"✓ Server time: {datetime.fromtimestamp(server_time['serverTime'] / 1000)}")
            
            # Test exchange info
            exchange_info = self.requests_client.get_exchange_info()
            symbol_count = len(exchange_info.get('symbols', []))
            self.logger.info(f"✓ Exchange info: {symbol_count} symbols available")
            
            # Test account access
            try:
                balance = self.requests_client.get_balance()
                self.logger.info(f"✓ Account access: {len(balance)} assets")
            except Exception as e:
                self.logger.warning(f"Account access limited: {e}")
            
            # Sync time
            self.time_sync.sync_time(self.requests_client)
            
            self.logger.info("✅ Connection test passed!")
            return True
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information with enhanced error handling"""
        try:
            # Get balance info
            balance_info = self.requests_client.get_balance()
            
            # Get position info  
            positions_info = self.requests_client.get_position_info()
            
            # Calculate totals
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
                'availableBalance': str(usdt_balance),  # Simplified
                'totalUnrealizedProfit': str(total_unrealized_pnl),
                'positions': positions_info,
                'assets': balance_info,
                'status': 'OK'
            }
            
        except Exception as e:
            self.logger.error(f"Error getting account info: {e}")
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
            price = float(ticker['price'])
            self.logger.info(f"Current price for {symbol}: {price}")
            return price
        except Exception as e:
            self.logger.error(f"Error getting price for {symbol}: {e}")
            raise
    
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict[str, Any]:
        """Place a market order"""
        try:
            self.logger.info(f"Placing market order: {side} {quantity} {symbol}")
            
            order = self.requests_client.place_order(
                symbol=symbol,
                side=side,
                order_type='MARKET',
                quantity=quantity
            )
            
            self.logger.info(f"Market order placed: {order}")
            return order
            
        except Exception as e:
            self.logger.error(f"Error placing market order: {e}")
            raise
    
    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict[str, Any]:
        """Place a limit order"""
        try:
            self.logger.info(f"Placing limit order: {side} {quantity} {symbol} at {price}")
            
            order = self.requests_client.place_order(
                symbol=symbol,
                side=side,
                order_type='LIMIT',
                quantity=quantity,
                price=price,
                timeInForce='GTC'
            )
            
            self.logger.info(f"Limit order placed: {order}")
            return order
            
        except Exception as e:
            self.logger.error(f"Error placing limit order: {e}")
            raise
    
    def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get open orders"""
        try:
            orders = self.requests_client.get_open_orders(symbol)
            self.logger.info(f"Retrieved {len(orders)} open orders")
            return orders
        except Exception as e:
            self.logger.error(f"Error getting open orders: {e}")
            return []
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an order"""
        try:
            result = self.requests_client.cancel_order(symbol, order_id)
            self.logger.info(f"Order cancelled: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error cancelling order: {e}")
            raise
    
    def get_order_status(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Get order status"""
        try:
            order = self.requests_client.get_order(symbol, order_id)
            self.logger.info(f"Order status: {order}")
            return order
        except Exception as e:
            self.logger.error(f"Error getting order status: {e}")
            raise
    
    def test_requests_features(self):
        """Test various requests-specific features"""
        results = {}
        
        # Test direct HTTP methods
        test_cases = [
            ('Server Time', lambda: self.requests_client.get_server_time()),
            ('Exchange Info', lambda: self.requests_client.get_exchange_info()),
            ('Account Balance', lambda: self.requests_client.get_balance()),
            ('Position Info', lambda: self.requests_client.get_position_info()),
            ('Open Orders', lambda: self.requests_client.get_open_orders()),
        ]
        
        for test_name, test_func in test_cases:
            try:
                result = test_func()
                results[test_name] = {
                    'status': 'SUCCESS',
                    'data_type': type(result).__name__,
                    'data_size': len(result) if isinstance(result, (list, dict)) else 'N/A'
                }
                self.logger.info(f"✓ {test_name}: SUCCESS")
            except Exception as e:
                results[test_name] = {
                    'status': 'FAILED', 
                    'error': str(e)
                }
                self.logger.warning(f"✗ {test_name}: FAILED - {e}")
        
        return results

class EnhancedTradingBotCLI:
    """Enhanced CLI with requests integration"""
    
    def __init__(self):
        self.bot = None
        self.logger = TradingBotLogger().get_logger()
    
    def initialize_bot(self, use_requests_only: bool = False):
        """Initialize the enhanced trading bot"""
        print("=== Enhanced Binance Futures Trading Bot ===")
        print("Initializing bot with API credentials...")
        
        # Get credentials
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        
        if not api_key or not api_secret:
            api_key = input("Enter your Binance API Key: ").strip()
            api_secret = input("Enter your Binance API Secret: ").strip()
        else:
            print("Using API credentials from environment variables")
        
        if not api_key or not api_secret:
            print("Error: API credentials are required")
            return False
        
        try:
            self.bot = EnhancedTradingBot(
                api_key, 
                api_secret, 
                testnet=True,
                use_requests_only=use_requests_only
            )
            print("✓ Enhanced bot initialized successfully!")
            return True
        except Exception as e:
            print(f"✗ Failed to initialize bot: {e}")
            return False
    
    def display_menu(self):
        """Display the main menu"""
        print("\n" + "="*60)
        print("         ENHANCED TRADING BOT MENU")
        print("="*60)
        print("1. Account Information")
        print("2. Get Current Price")
        print("3. Place Market Order")
        print("4. Place Limit Order")
        print("5. View Open Orders")
        print("6. Cancel Order")
        print("7. Get Order Status")
        print("8. Test Requests Features")
        print("9. Switch Client Mode")
        print("10. HTTP Request Demo")
        print("0. Exit")
        print("="*60)
    
    def handle_requests_test(self):
        """Handle requests features test"""
        try:
            print("\n--- Testing Requests Features ---")
            results = self.bot.test_requests_features()
            
            print("\nRequests Client Test Results:")
            for test_name, result in results.items():
                status_symbol = "✓" if result['status'] == 'SUCCESS' else "✗"
                print(f"{status_symbol} {test_name}: {result['status']}")
                if result['status'] == 'SUCCESS':
                    print(f"  Data Type: {result['data_type']}")
                    print(f"  Data Size: {result['data_size']}")
                else:
                    print(f"  Error: {result['error']}")
        except Exception as e:
            print(f"Error testing requests features: {e}")
    
    def handle_http_demo(self):
        """Demonstrate raw HTTP requests"""
        try:
            print("\n--- HTTP Request Demo ---")
            
            # Demo 1: Public endpoint (no auth)
            print("1. Testing public endpoint (server time):")
            response = requests.get("https://testnet.binancefuture.com/fapi/v1/time")
            if response.status_code == 200:
                data = response.json()
                server_time = datetime.fromtimestamp(data['serverTime'] / 1000)
                print(f"   ✓ Server Time: {server_time}")
            else:
                print(f"   ✗ Failed: {response.status_code}")
            
            # Demo 2: Custom headers
            print("\n2. Testing with custom headers:")
            headers = {
                'User-Agent': 'Enhanced-Trading-Bot/1.0',
                'Accept': 'application/json'
            }
            response = requests.get(
                "https://testnet.binancefuture.com/fapi/v1/exchangeInfo", 
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Exchange Info: {len(data.get('symbols', []))} symbols")
            else:
                print(f"   ✗ Failed: {response.status_code}")
                
            # Demo 3: Session usage
            print("\n3. Testing with session:")
            session = requests.Session()
            session.headers.update({'User-Agent': 'SessionBot/1.0'})
            
            response = session.get("https://testnet.binancefuture.com/fapi/v1/ping")
            if response.status_code == 200:
                print("   ✓ Ping successful with session")
            else:
                print(f"   ✗ Ping failed: {response.status_code}")
                
        except Exception as e:
            print(f"HTTP demo error: {e}")
    
    def run(self):
        """Run the enhanced CLI"""
        mode_choice = input("Use requests-only mode? (y/n): ").strip().lower()
        use_requests_only = mode_choice == 'y'
        
        if not self.initialize_bot(use_requests_only):
            return
        
        while True:
            try:
                self.display_menu()
                choice = input("\nEnter your choice (0-10): ").strip()
                
                if choice == '0':
                    print("Goodbye!")
                    break
                elif choice == '1':
                    self.handle_account_info()
                elif choice == '2':
                    self.handle_current_price()
                elif choice == '3':
                    self.handle_market_order()
                elif choice == '4':
                    self.handle_limit_order()
                elif choice == '5':
                    self.handle_open_orders()
                elif choice == '6':
                    self.handle_cancel_order()
                elif choice == '7':
                    self.handle_order_status()
                elif choice == '8':
                    self.handle_requests_test()
                elif choice == '9':
                    print("Restart the bot to switch client mode")
                elif choice == '10':
                    self.handle_http_demo()
                else:
                    print("Invalid choice. Please try again.")
                
                input("\nPress Enter to continue...")
                
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                self.logger.error(f"CLI error: {e}")
    
    # Import other CLI methods from the original class
    def handle_account_info(self):
        """Handle account information request"""
        try:
            print("\n--- Account Information ---")
            account_info = self.bot.get_account_info()
            
            def safe_float_convert(value, default=0.0):
                if value is None or value == 'N/A' or value == '':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            total_balance = safe_float_convert(account_info.get('totalWalletBalance', 'N/A'))
            available_balance = safe_float_convert(account_info.get('availableBalance', 'N/A'))
            unrealized_pnl = safe_float_convert(account_info.get('totalUnrealizedProfit', 'N/A'))
            
            print(f"Total Wallet Balance: {total_balance} USDT")
            print(f"Available Balance: {available_balance} USDT")
            print(f"Total Unrealized PnL: {unrealized_pnl} USDT")
            
            if 'status' in account_info:
                print(f"Status: {account_info['status']}")
                
        except Exception as e:
            print(f"Error getting account info: {e}")
    
    def handle_current_price(self):
        """Handle current price request"""
        try:
            symbol = input("Enter symbol (e.g., BTCUSDT): ").strip()
            price = self.bot.get_current_price(symbol)
            print(f"\nCurrent price for {symbol.upper()}: {price} USDT")
        except Exception as e:
            print(f"Error getting current price: {e}")
    
    def handle_market_order(self):
        """Handle market order placement"""
        try:
            print("\n--- Place Market Order ---")
            print("⚠️  WARNING: This will place a real order on testnet!")
            confirm = input("Type 'YES' to confirm: ").strip()
            if confirm != 'YES':
                print("Order cancelled")
                return
                
            symbol = input("Enter symbol (e.g., BTCUSDT): ").strip()
            side = input("Enter side (BUY/SELL): ").strip().upper()
            quantity = float(input("Enter quantity: ").strip())
            
            if side not in ['BUY', 'SELL']:
                print("Error: Side must be BUY or SELL")
                return
            
            print(f"\nPlacing market order: {side} {quantity} {symbol}")
            order = self.bot.place_market_order(symbol, side, quantity)
            
            print("✓ Market order placed successfully!")
            print(f"Order ID: {order.get('orderId')}")
            print(f"Status: {order.get('status')}")
            
        except Exception as e:
            print(f"Error placing market order: {e}")
    
    def handle_limit_order(self):
        """Handle limit order placement"""
        try:
            print("\n--- Place Limit Order ---")
            symbol = input("Enter symbol (e.g., BTCUSDT): ").strip()
            side = input("Enter side (BUY/SELL): ").strip().upper()
            quantity = float(input("Enter quantity: ").strip())
            price = float(input("Enter price: ").strip())
            
            if side not in ['BUY', 'SELL']:
                print("Error: Side must be BUY or SELL")
                return
            
            print(f"\nPlacing limit order: {side} {quantity} {symbol} at {price}")
            order = self.bot.place_limit_order(symbol, side, quantity, price)
            
            print("✓ Limit order placed successfully!")
            print(f"Order ID: {order.get('orderId')}")
            print(f"Status: {order.get('status')}")
            
        except Exception as e:
            print(f"Error placing limit order: {e}")
    
    def handle_open_orders(self):
        """Handle open orders request"""
        try:
            print("\n--- Open Orders ---")
            symbol = input("Enter symbol (optional, press Enter for all): ").strip()
            symbol = symbol if symbol else None
            
            orders = self.bot.get_open_orders(symbol)
            
            if not orders:
                print("No open orders found")
                return
            
            print(f"\nFound {len(orders)} open order(s):")
            for order in orders:
                print(f"Order ID: {order.get('orderId')}")
                print(f"Symbol: {order.get('symbol')}")
                print(f"Side: {order.get('side')}")
                print(f"Type: {order.get('type')}")
                print(f"Quantity: {order.get('origQty')}")
                print(f"Price: {order.get('price')}")
                print(f"Status: {order.get('status')}")
                print("-" * 40)
                
        except Exception as e:
            print(f"Error getting open orders: {e}")
    
    def handle_cancel_order(self):
        """Handle order cancellation"""
        try:
            print("\n--- Cancel Order ---")
            symbol = input("Enter symbol (e.g., BTCUSDT): ").strip()
            order_id = int(input("Enter order ID: ").strip())
            
            result = self.bot.cancel_order(symbol, order_id)
            
            print("✓ Order cancelled successfully!")
            print(f"Order ID: {result.get('orderId')}")
            print(f"Status: {result.get('status')}")
            
        except Exception as e:
            print(f"Error cancelling order: {e}")
    
    def handle_order_status(self):
        """Handle order status request"""
        try:
            print("\n--- Order Status ---")
            symbol = input("Enter symbol (e.g., BTCUSDT): ").strip()
            order_id = int(input("Enter order ID: ").strip())
            
            order = self.bot.get_order_status(symbol, order_id)
            
            print(f"\nOrder Status for ID {order_id}:")
            print(f"Symbol: {order.get('symbol')}")
            print(f"Side: {order.get('side')}")
            print(f"Type: {order.get('type')}")
            print(f"Original Quantity: {order.get('origQty')}")
            print(f"Executed Quantity: {order.get('executedQty')}")
            print(f"Price: {order.get('price')}")
            print(f"Status: {order.get('status')}")
            print(f"Time in Force: {order.get('timeInForce')}")
            
        except Exception as e:
            print(f"Error getting order status: {e}")


def main():
    """Main function to run the enhanced trading bot CLI"""
    parser = argparse.ArgumentParser(description='Enhanced Binance Futures Trading Bot')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--requests-only', action='store_true', help='Use requests-only mode')
    
    args = parser.parse_args()
    
    # Set logging level
    log_level = logging.DEBUG if args.debug else logging.INFO
    
    try:
        cli = EnhancedTradingBotCLI()
        cli.run()
    except KeyboardInterrupt:
        print("\n\nBot terminated by user.")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()