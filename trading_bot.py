#!/usr/bin/env python3
"""
Fixed Trading Bot for Binance Futures Testnet with Timestamp Synchronization
Author: Trading Bot Implementation
Description: A comprehensive trading bot with timestamp sync and enhanced error handling
"""

import os
import sys
import json
import logging
import argparse
import time
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv
load_dotenv()  # This loads the .env file

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    from binance.enums import *
except ImportError:
    print("Error: python-binance library not installed. Install with: pip install python-binance")
    sys.exit(1)

class TimestampSync:
    """Handle timestamp synchronization with Binance servers"""
    
    def __init__(self):
        self.time_offset = 0
        self.last_sync = 0
        self.sync_interval = 300  # Sync every 5 minutes
    
    def sync_time(self, client):
        """Synchronize time with Binance server"""
        try:
            # Get server time
            server_time_response = client.futures_time()
            server_time = server_time_response['serverTime']
            
            # Get local time in milliseconds
            local_time = int(time.time() * 1000)
            
            # Calculate offset
            self.time_offset = server_time - local_time
            self.last_sync = time.time()
            
            print(f"Time synchronized. Offset: {self.time_offset}ms")
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

class BasicBot:
    """Fixed Trading Bot for Binance Futures Testnet with Timestamp Sync"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        Initialize the trading bot
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet environment (default: True)
        """
        self.testnet = testnet
        self.logger = TradingBotLogger().get_logger()
        self.time_sync = TimestampSync()
        
        try:
            # Initialize client for testnet
            if testnet:
                self.client = Client(
                    api_key=api_key,
                    api_secret=api_secret,
                    testnet=True
                )
                self.logger.info("Using Binance Futures Testnet")
            else:
                self.client = Client(
                    api_key=api_key,
                    api_secret=api_secret,
                    testnet=False
                )
                self.logger.info("Using Binance Futures Mainnet")
            
            # Synchronize time with server
            print("Synchronizing time with Binance servers...")
            if not self.time_sync.sync_time(self.client):
                print("Warning: Time synchronization failed. Proceeding anyway.")
            
            self.logger.info("Trading bot initialized successfully")
            self._test_connection()
            
        except Exception as e:
            self.logger.error(f"Failed to initialize trading bot: {e}")
            self._log_detailed_error(e)
            raise
    
    def _ensure_time_sync(self):
        """Ensure time is synchronized before API calls"""
        if self.time_sync.should_resync():
            self.time_sync.sync_time(self.client)
    
    def _log_detailed_error(self, error):
        """Log detailed error information"""
        if isinstance(error, BinanceAPIException):
            self.logger.error(f"Binance API Error Details:")
            self.logger.error(f"  Status Code: {error.status_code}")
            self.logger.error(f"  Error Code: {error.code}")
            self.logger.error(f"  Error Message: {error.message}")
            if hasattr(error, 'response') and error.response:
                self.logger.error(f"  Full Response: {error.response}")
                
            # Specific handling for timestamp errors
            if error.code == -1021:
                print("\n🕐 TIMESTAMP ERROR DETECTED!")
                print("Your system time is not synchronized with Binance servers.")
                print("Solutions:")
                print("1. Synchronize your system clock")
                print("2. Use NTP time synchronization")
                print("3. Restart the bot (it will auto-sync)")
                
                # Try to resync time
                print("Attempting to resync time...")
                if self.time_sync.sync_time(self.client):
                    print("✓ Time resynchronized successfully!")
                else:
                    print("✗ Time resync failed")
        else:
            self.logger.error(f"General Error: {str(error)}")
            self.logger.error(f"Error Type: {type(error).__name__}")
    
    def _test_connection(self):
        """Test API connection and log account information"""
        try:
            self.logger.info("Testing API connection...")
            
            # Test server time first
            server_time = self.client.futures_time()
            self.logger.info(f"Server time: {datetime.fromtimestamp(server_time['serverTime'] / 1000)}")
            
            # Test account info with detailed error handling
            try:
                account_info = self.client.futures_account()
                self.logger.info("API connection successful - futures_account() worked")
                balance = account_info.get('totalWalletBalance', '0')
                self.logger.info(f"Account balance: {balance} USDT")
                return True
            except BinanceAPIException as e:
                if e.code == -1021:
                    print("Time synchronization issue detected during connection test.")
                    self._log_detailed_error(e)
                    return False
                    
                self.logger.warning(f"futures_account() failed: {e.message} (Code: {e.code})")
                self._log_detailed_error(e)
                
                # Try alternative method for testnet
                self.logger.info("Trying alternative API methods...")
                
                try:
                    balance = self.client.futures_account_balance()
                    self.logger.info("Alternative API connection successful - futures_account_balance() worked")
                    total_balance = sum(float(b['balance']) for b in balance if b['asset'] == 'USDT')
                    self.logger.info(f"USDT Balance: {total_balance}")
                    return True
                except Exception as e2:
                    self.logger.error(f"Alternative API method also failed: {e2}")
                    self._log_detailed_error(e2)
                    
                    # Try even more basic test
                    try:
                        positions = self.client.futures_position_information()
                        self.logger.info("Basic API test successful - futures_position_information() worked")
                        return True
                    except Exception as e3:
                        self.logger.error(f"Basic API test also failed: {e3}")
                        self._log_detailed_error(e3)
                        return False
            
        except Exception as e:
            self.logger.error(f"API connection test failed: {e}")
            self._log_detailed_error(e)
            return False
    
    def _safe_float_conversion(self, value, default=0.0):
        """Safely convert a value to float, returning default if conversion fails"""
        try:
            if value is None or value == 'N/A' or value == '':
                return default
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information with enhanced error handling and time sync"""
        try:
            self._ensure_time_sync()
            self.logger.info("Attempting to get account information...")
            
            # Try primary method first
            try:
                account_info = self.client.futures_account()
                if account_info is None:
                    raise Exception("futures_account() returned None")
                self.logger.info("Account information retrieved successfully using futures_account()")
                return account_info
            except BinanceAPIException as e:
                if e.code == -1021:
                    print("Timestamp error detected. Attempting to resync...")
                    if self.time_sync.sync_time(self.client):
                        print("Time resynced. Retrying...")
                        account_info = self.client.futures_account()
                        if account_info is None:
                            raise Exception("futures_account() returned None after time sync")
                        return account_info
                    else:
                        raise Exception("Failed to sync time and retrieve account info")
                
                self.logger.warning(f"futures_account() failed with error {e.code}: {e.message}")
                self._log_detailed_error(e)
                
                # Try alternative methods
                self.logger.info("Trying alternative methods to get account information...")
                
                try:
                    # Method 1: Get balance and positions separately
                    balance = self.client.futures_account_balance()
                    positions = self.client.futures_position_information()
                    
                    # Check if responses are None
                    if balance is None:
                        balance = []
                    if positions is None:
                        positions = []
                    
                    # Construct account info from separate calls
                    usdt_balance = 0
                    available_balance = 0
                    for b in balance:
                        if b and b.get('asset') == 'USDT':
                            usdt_balance = self._safe_float_conversion(b.get('balance', 0))
                            available_balance = self._safe_float_conversion(b.get('availableBalance', 0))
                            break
                    
                    total_unrealized_pnl = 0
                    for p in positions:
                        if p and p.get('unrealizedProfit'):
                            total_unrealized_pnl += self._safe_float_conversion(p.get('unrealizedProfit', 0))
                    
                    account_info = {
                        'totalWalletBalance': str(usdt_balance),
                        'availableBalance': str(available_balance),
                        'totalUnrealizedProfit': str(total_unrealized_pnl),
                        'positions': positions,
                        'assets': balance
                    }
                    
                    self.logger.info("Account information retrieved using alternative method")
                    return account_info
                    
                except Exception as e2:
                    if isinstance(e2, BinanceAPIException) and e2.code == -1021:
                        print("Timestamp error in alternative method. Please check your system time.")
                        
                    self.logger.error(f"Alternative method 1 failed: {e2}")
                    self._log_detailed_error(e2)
                    
                    # Return safe fallback with numeric values instead of 'N/A'
                    return {
                        'totalWalletBalance': '0.0',
                        'availableBalance': '0.0',
                        'totalUnrealizedProfit': '0.0',
                        'positions': [],
                        'assets': [],
                        'status': 'API Error - Limited access',
                        'error': True
                    }
                
                raise
        except Exception as e:
            self.logger.error(f"Unexpected error getting account info: {e}")
            self._log_detailed_error(e)
            # Return safe fallback instead of raising
            return {
                'totalWalletBalance': '0.0',
                'availableBalance': '0.0',
                'totalUnrealizedProfit': '0.0',
                'positions': [],
                'assets': [],
                'status': 'Unexpected Error',
                'error': True
            }
    
    def get_account_balance_safe(self) -> Dict[str, float]:
        """Get account balance with safe float conversion"""
        try:
            account_info = self.get_account_info()
            
            return {
                'total_balance': self._safe_float_conversion(account_info.get('totalWalletBalance', 0)),
                'available_balance': self._safe_float_conversion(account_info.get('availableBalance', 0)),
                'unrealized_pnl': self._safe_float_conversion(account_info.get('totalUnrealizedProfit', 0)),
                'has_error': account_info.get('error', False)
            }
        except Exception as e:
            self.logger.error(f"Error getting safe account balance: {e}")
            return {
                'total_balance': 0.0,
                'available_balance': 0.0,
                'unrealized_pnl': 0.0,
                'has_error': True
            }
    
    def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get open orders with enhanced error handling and timestamp sync"""
        try:
            self._ensure_time_sync()
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if symbol:
                        orders = self.client.futures_get_open_orders(symbol=symbol.upper())
                    else:
                        orders = self.client.futures_get_open_orders()
                    
                    if orders is None:
                        orders = []
                    
                    self.logger.info(f"Retrieved {len(orders)} open orders")
                    return orders
                    
                except BinanceAPIException as e:
                    if e.code == -1021:
                        print(f"Timestamp error (attempt {attempt + 1}/{max_retries}). Resyncing time...")
                        if self.time_sync.sync_time(self.client):
                            print("Time resynced. Retrying...")
                            time.sleep(0.5)  # Small delay before retry
                            continue
                        else:
                            print("Failed to sync time")
                    
                    self.logger.error(f"Binance API error getting open orders: {e}")
                    self._log_detailed_error(e)
                    if attempt == max_retries - 1:  # Last attempt
                        return []  # Return empty list instead of raising
                    else:
                        time.sleep(1)  # Wait before retry
                        
        except Exception as e:
            self.logger.error(f"Unexpected error getting open orders: {e}")
            self._log_detailed_error(e)
            return []  # Return empty list instead of raising
    
    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Get symbol information and trading rules"""
        try:
            self._ensure_time_sync()
            exchange_info = self.client.futures_exchange_info()
            symbol_info = None
            
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol.upper():
                    symbol_info = s
                    break
            
            if not symbol_info:
                raise ValueError(f"Symbol {symbol} not found")
            
            self.logger.info(f"Symbol info retrieved for {symbol}")
            return symbol_info
        except Exception as e:
            self.logger.error(f"Error getting symbol info for {symbol}: {e}")
            self._log_detailed_error(e)
            raise
    
    def _validate_order_params(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None) -> tuple:
        """Validate order parameters"""
        try:
            # Get symbol info for validation
            symbol_info = self.get_symbol_info(symbol)
            
            # Validate side
            if side.upper() not in ['BUY', 'SELL']:
                raise ValueError("Side must be 'BUY' or 'SELL'")
            
            # Validate order type
            valid_types = ['MARKET', 'LIMIT', 'STOP_MARKET', 'STOP', 'TAKE_PROFIT_MARKET', 'TAKE_PROFIT']
            if order_type.upper() not in valid_types:
                raise ValueError(f"Order type must be one of: {valid_types}")
            
            # Get filters
            filters = symbol_info.get('filters')
            if not filters:
                raise ValueError(f"No filters found for symbol: {symbol}")

            filters = {f['filterType']: f for f in filters}

            lot_size = filters.get('LOT_SIZE')
            if lot_size is None:
                raise ValueError(f"LOT_SIZE filter missing for {symbol}")
            
            min_qty = float(lot_size.get('minQty', 0))
            max_qty = float(lot_size.get('maxQty', float('inf')))
            step_size = float(lot_size.get('stepSize', 1))
            
            if quantity < min_qty:
                raise ValueError(f"Quantity {quantity} is below minimum {min_qty}")
            if quantity > max_qty:
                raise ValueError(f"Quantity {quantity} exceeds maximum {max_qty}")
            
            # Round quantity to step size
            quantity = float(Decimal(str(quantity)).quantize(
                Decimal(str(step_size)), rounding=ROUND_DOWN
            ))
            
            # Validate price for limit orders
            if order_type.upper() in ['LIMIT', 'STOP', 'TAKE_PROFIT'] and price is not None:
                price_filter = filters.get('PRICE_FILTER')
                if price_filter is None:
                    raise ValueError(f"PRICE_FILTER filter missing for {symbol}")
                min_price = float(price_filter.get('minPrice', 0))
                max_price = float(price_filter.get('maxPrice', float('inf')))
                tick_size = float(price_filter.get('tickSize', 0.01))

                if price < min_price:
                    raise ValueError(f"Price {price} is below minimum {min_price}")
                if price > max_price:
                    raise ValueError(f"Price {price} exceeds maximum {max_price}")

                price = float(Decimal(str(price)).quantize(
                        Decimal(str(tick_size)), rounding=ROUND_DOWN
                    ))
                # Round price to tick size
                price = float(Decimal(str(price)).quantize(
                    Decimal(str(tick_size)), rounding=ROUND_DOWN
                ))
            
            return quantity, price
            
        except Exception as e:
            self.logger.error(f"Order validation failed: {e}")
            self._log_detailed_error(e)
            raise
   
    def _safe_order_response(self, order_response):
        """Safely handle order response that might be None"""
        if order_response is None:
            self.logger.error("Order response is None — this should not happen unless the API call failed silently.")
            return {
                'orderId': 'Unknown',
                'status': 'Error - No response received',
                'executedQty': '0',
                'cummulativeQuoteQty': '0',
                'price': '0',
                'stopPrice': '0',
                'symbol': 'Unknown',
                'side': 'Unknown',
                'type': 'Unknown',
                'origQty': '0',
                'avgPrice': '0',
                'time': 0
            }
        return order_response
    
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict[str, Any]:
        """Place a market order with enhanced error handling and timestamp sync"""
        order = self.client.futures_create_order(...)
        self.logger.debug(f"Raw order response: {order}")  
        try:
            self._ensure_time_sync()

            # Validate parameters
            quantity, _ = self._validate_order_params(symbol, side, 'MARKET', quantity)

            self.logger.info(f"Placing market order: {side} {quantity} {symbol}")

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    order = self.client.futures_create_order(
                        symbol=symbol.upper(),
                        side=side.upper(),
                        type=ORDER_TYPE_MARKET,
                        quantity=quantity
                    )

                    self.logger.debug(f"Raw order response: {order}")  # Log raw response
                    order = self._safe_order_response(order)

                    self.logger.info(f"Market order placed successfully: {order}")
                    return order

                except BinanceAPIException as e:
                    if e.code == -1021:
                        print(f"Timestamp error in order placement (attempt {attempt + 1}/{max_retries})")
                        if self.time_sync.sync_time(self.client):
                            print("Time resynced. Retrying order...")
                            time.sleep(0.5)
                            continue

                    self.logger.error(f"Binance API error placing market order: {e}")
                    self._log_detailed_error(e)

                    # Specific error guidance
                    if e.code == -2019:
                        print("Error: Insufficient margin balance")
                    elif e.code == -1013:
                        print("Error: Invalid quantity or price filter")
                    elif e.code == -4014:
                        print("Error: Price exceeds maximum allowed")

                    if attempt == max_retries - 1:
                        raise
                    else:
                        time.sleep(1)

        except Exception as e:
            self.logger.error(f"Unexpected error placing market order: {e}")
            self._log_detailed_error(e)
            raise

    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict[str, Any]:
        """Place a limit order with enhanced error handling and timestamp sync"""
        try:
            self._ensure_time_sync()

            # Validate parameters
            quantity, price = self._validate_order_params(symbol, side, 'LIMIT', quantity, price)

            self.logger.info(f"Placing limit order: {side} {quantity} {symbol} at {price}")

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    order = self.client.futures_create_order(
                        symbol=symbol.upper(),
                        side=side.upper(),
                        type=ORDER_TYPE_LIMIT,
                        timeInForce=TIME_IN_FORCE_GTC,
                        quantity=quantity,
                        price=price
                    )

                    self.logger.debug(f"Raw order response: {order}")  # Log raw response
                    order = self._safe_order_response(order)

                    self.logger.info(f"Limit order placed successfully: {order}")
                    return order

                except BinanceAPIException as e:
                    if e.code == -1021:
                        print(f"Timestamp error in limit order (attempt {attempt + 1}/{max_retries})")
                        if self.time_sync.sync_time(self.client):
                            print("Time resynced. Retrying order...")
                            time.sleep(0.5)
                            continue

                    self.logger.error(f"Binance API error placing limit order: {e}")
                    self._log_detailed_error(e)

                    if e.code == -2019:
                        print("Error: Insufficient margin balance")
                    elif e.code == -1013:
                        print("Error: Invalid quantity or price filter")
                    elif e.code == -4014:
                        print("Error: Price exceeds maximum allowed")

                    if attempt == max_retries - 1:
                        raise
                    else:
                        time.sleep(1)

        except Exception as e:
            self.logger.error(f"Unexpected error placing limit order: {e}")
            self._log_detailed_error(e)
            raise

    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an order with enhanced error handling and timestamp sync"""
        try:
            self._ensure_time_sync()
            self.logger.info(f"Cancelling order {order_id} for {symbol}")
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = self.client.futures_cancel_order(
                        symbol=symbol.upper(),
                        orderId=order_id
                    )
                    
                    self.logger.info(f"Order cancelled successfully: {result}")
                    return result
                    
                except BinanceAPIException as e:
                    if e.code == -1021:
                        print(f"Timestamp error in cancel order (attempt {attempt + 1}/{max_retries})")
                        if self.time_sync.sync_time(self.client):
                            print("Time resynced. Retrying cancel...")
                            time.sleep(0.5)
                            continue
                    
                    self.logger.error(f"Binance API error cancelling order: {e}")
                    self._log_detailed_error(e)
                    
                    if attempt == max_retries - 1:
                        raise
                    else:
                        time.sleep(1)
                        
        except Exception as e:
            self.logger.error(f"Unexpected error cancelling order: {e}")
            self._log_detailed_error(e)
            raise
    
    def get_order_status(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Get order status with enhanced error handling and timestamp sync"""
        try:
            self._ensure_time_sync()
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    order = self.client.futures_get_order(
                        symbol=symbol.upper(),
                        orderId=order_id
                    )
                    
                    self.logger.info(f"Order status retrieved: {order}")
                    return order
                    
                except BinanceAPIException as e:
                    if e.code == -1021:
                        print(f"Timestamp error in get order status (attempt {attempt + 1}/{max_retries})")
                        if self.time_sync.sync_time(self.client):
                            print("Time resynced. Retrying...")
                            time.sleep(0.5)
                            continue
                    
                    self.logger.error(f"Binance API error getting order status: {e}")
                    self._log_detailed_error(e)
                    
                    if attempt == max_retries - 1:
                        raise
                    else:
                        time.sleep(1)
                        
        except Exception as e:
            self.logger.error(f"Unexpected error getting order status: {e}")
            self._log_detailed_error(e)
            raise
    
    def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol with enhanced error handling and timestamp sync"""
        try:
            self._ensure_time_sync()
            ticker = self.client.futures_symbol_ticker(symbol=symbol.upper())
            price = float(ticker['price'])
            self.logger.info(f"Current price for {symbol}: {price}")
            return price
            
        except BinanceAPIException as e:
            if e.code == -1021:
                print("Timestamp error getting price. Resyncing...")
                if self.time_sync.sync_time(self.client):
                    ticker = self.client.futures_symbol_ticker(symbol=symbol.upper())
                    price = float(ticker['price'])
                    return price
            
            self.logger.error(f"Binance API error getting price: {e}")
            self._log_detailed_error(e)
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error getting price: {e}")
            self._log_detailed_error(e)
            raise
    
    def test_api_permissions(self):
        """Test various API endpoints to check permissions"""
        results = {}
        
        # Ensure time sync before testing
        self._ensure_time_sync()
        
        test_functions = [
            ('Server Time', lambda: self.client.futures_time()),
            ('Exchange Info', lambda: self.client.futures_exchange_info()),
            ('Account Balance', lambda: self.client.futures_account_balance()),
            ('Position Info', lambda: self.client.futures_position_information()),
            ('Account Info', lambda: self.client.futures_account()),
            ('Open Orders', lambda: self.client.futures_get_open_orders()),
        ]
        
        for test_name, test_func in test_functions:
            try:
                result = test_func()
                results[test_name] = {'status': 'SUCCESS', 'data': 'Available'}
                self.logger.info(f"{test_name}: SUCCESS")
            except BinanceAPIException as e:
                if e.code == -1021:
                    # Try to resync and retry once
                    try:
                        self.time_sync.sync_time(self.client)
                        result = test_func()
                        results[test_name] = {'status': 'SUCCESS (after time sync)', 'data': 'Available'}
                        self.logger.info(f"{test_name}: SUCCESS (after time sync)")
                    except Exception as e2:
                        results[test_name] = {'status': 'FAILED', 'error': f"Code {e.code}: {e.message}"}
                        self.logger.warning(f"{test_name}: FAILED - {e.code}: {e.message}")
                else:
                    results[test_name] = {'status': 'FAILED', 'error': f"Code {e.code}: {e.message}"}
                    self.logger.warning(f"{test_name}: FAILED - {e.code}: {e.message}")
            except Exception as e:
                results[test_name] = {'status': 'ERROR', 'error': str(e)}
                self.logger.error(f"{test_name}: ERROR - {e}")
        
        return results

class TradingBotCLI:
    """Command Line Interface for the Trading Bot with enhanced diagnostics"""
    
    def __init__(self):
        self.bot = None
        self.logger = TradingBotLogger().get_logger()
    
    def initialize_bot(self):
        """Initialize the trading bot with API credentials"""
        print("=== Binance Futures Trading Bot ===")
        print("Initializing bot with API credentials...")
        
        # Try to get credentials from environment first
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        
        if not api_key or not api_secret:
            # Get API credentials from user input
            api_key = input("Enter your Binance API Key: ").strip()
            api_secret = input("Enter your Binance API Secret: ").strip()
        else:
            print("Using API credentials from environment variables")
        
        if not api_key or not api_secret:
            print("Error: API credentials are required")
            return False
        
        try:
            self.bot = BasicBot(api_key, api_secret, testnet=True)
            print("✓ Bot initialized successfully!")
            
            # Run API permissions test
            print("\nTesting API permissions...")
            test_results = self.bot.test_api_permissions()
            
            print("\nAPI Test Results:")
            for test_name, result in test_results.items():
                status_symbol = "✓" if result['status'] == 'SUCCESS' else "✗"
                print(f"  {status_symbol} {test_name}: {result['status']}")
                if result['status'] != 'SUCCESS':
                    print(f"    Error: {result.get('error', 'Unknown error')}")
            
            return True
        except Exception as e:
            print(f"✗ Failed to initialize bot: {e}")
            return False
    
    def display_menu(self):
        """Display the main menu"""
        print("\n" + "="*50)
        print("         TRADING BOT MENU")
        print("="*50)
        print("1. Account Information")
        print("2. Get Current Price")
        print("3. Place Market Order")
        print("4. Place Limit Order")
        print("5. View Open Orders")
        print("6. Cancel Order")
        print("7. Get Order Status")
        print("8. Test API Permissions")
        print("9. Log Files Location")
        print("0. Exit")
        print("="*50)
    
    def get_user_input(self, prompt: str, input_type: type = str, required: bool = True):
        """Get validated user input"""
        while True:
            try:
                value = input(f"{prompt}: ").strip()
                if not value and required:
                    print("This field is required. Please enter a value.")
                    continue
                if not value and not required:
                    return None
                return input_type(value)
            except ValueError:
                print(f"Invalid input. Please enter a valid {input_type.__name__}.")
    
    def handle_account_info(self):
        """Handle account information request with detailed error display"""
    try:
        print("\n--- Account Information ---")
        account_info = self.bot.get_account_info()
        
        # Safe conversion function for balance values
        def safe_float_convert(value, default=0.0):
            """Safely convert string to float, handling 'N/A' and None values"""
            if value is None or value == 'N/A' or value == '':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        # Safe display of balance information
        total_balance = safe_float_convert(account_info.get('totalWalletBalance', 'N/A'))
        available_balance = safe_float_convert(account_info.get('availableBalance', 'N/A'))
        unrealized_pnl = safe_float_convert(account_info.get('totalUnrealizedProfit', 'N/A'))

        
        print(f"Total Wallet Balance: {total_balance} USDT")
        print(f"Available Balance: {available_balance} USDT")
        print(f"Total Unrealized PnL: {unrealized_pnl} USDT")
        
        # Show status if available
        if 'status' in account_info:
            print(f"Status: {account_info['status']}")
        
        # Show positions with safe float handling
        positions = account_info.get('positions', [])
        if positions:
            active_positions = []
            for p in positions:
                position_amt = safe_float_convert(p.get('positionAmt', 0))
                if position_amt != 0:
                    active_positions.append(p)
            
            if active_positions:
                print("\nActive Positions:")
                for pos in active_positions:
                    pos_amt = pos.get('positionAmt', '0')
                    unrealized_profit = pos.get('unrealizedProfit', '0')
                    print(f"  {pos['symbol']}: {pos_amt} (PnL: {unrealized_profit})")
            else:
                print("\nNo active positions")
        
        # Show assets if available with safe float handling
        assets = account_info.get('assets', [])
        if assets:
            print("\nAsset Balance:")
            for asset in assets:
                balance = safe_float_convert(asset.get('balance', 0))
                if balance > 0:
                    print(f"  {asset['asset']}: {asset['balance']}")
            
    except Exception as e:
        print(f"Error getting account info: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if your API key has Futures trading permissions")
        print("2. Ensure your API key is enabled for testnet if using testnet")
        print("3. Check if your IP is whitelisted (if IP restriction is enabled)")
        print("4. Verify your system time is synchronized")

    def _safe_order_response(self, order_response):
        """Safely handle order response that might be None"""
        if order_response is None:
            return {
                'orderId': 'Unknown',
                'status': 'Error - No response received',
                'executedQty': '0',
                'cummulativeQuoteQty': '0',
                'price': '0',
                'stopPrice': '0',
                'symbol': 'Unknown',
                'side': 'Unknown',
                'type': 'Unknown',
                'origQty': '0',
                'avgPrice': '0',
                'time': 0
            }
        return order_response

    def handle_test_api_permissions(self):
        """Handle API permissions test"""
        try:
            print("\n--- API Permissions Test ---")
            test_results = self.bot.test_api_permissions()
            
            print("\nDetailed API Test Results:")
            for test_name, result in test_results.items():
                status_symbol = "✓" if result['status'] == 'SUCCESS' else "✗"
                print(f"\n{status_symbol} {test_name}")
                print(f"  Status: {result['status']}")
                if result['status'] != 'SUCCESS':
                    print(f"  Error: {result.get('error', 'Unknown error')}")
            
            # Provide recommendations
            failed_tests = [name for name, result in test_results.items() if result['status'] != 'SUCCESS']
            if failed_tests:
                print(f"\n⚠️  {len(failed_tests)} test(s) failed. Recommendations:")
                if 'Account Info' in failed_tests or 'Account Balance' in failed_tests:
                    print("  - Check if your API key has 'Enable Futures' permission")
                    print("  - Ensure you're using the correct testnet API key")
                if 'Open Orders' in failed_tests:
                    print("  - Your API key might have read-only permissions")
            else:
                print("\n✅ All tests passed! Your API key is properly configured.")
                
        except Exception as e:
            print(f"Error testing API permissions: {e}")
    
    def run(self):
        """Run the CLI interface"""
        if not self.initialize_bot():
            return
        
        while True:
            try:
                self.display_menu()
                choice = input("\nEnter your choice (0-9): ").strip()
                
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
                    self.handle_test_api_permissions()
                elif choice == '9':
                    self.show_log_location()
                else:
                    print("Invalid choice. Please try again.")
                
                input("\nPress Enter to continue...")
                
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                self.logger.error(f"CLI error: {e}")
    
    # ... (rest of the CLI methods remain the same)
    def handle_current_price(self):
        """Handle current price request"""
        try:
            symbol = self.get_user_input("Enter symbol (e.g., BTCUSDT)")
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
                
            symbol = self.get_user_input("Enter symbol (e.g., BTCUSDT)")
            side = self.get_user_input("Enter side (BUY/SELL)").upper()
            quantity = self.get_user_input("Enter quantity", float)
            
            if side not in ['BUY', 'SELL']:
                print("Error: Side must be BUY or SELL")
                return
            
            # Show current price for reference
            try:
                current_price = self.bot.get_current_price(symbol)
                print(f"Current price: {current_price}")
            except:
                pass
            
            print(f"\nPlacing market order: {side} {quantity} {symbol}")
            order = self.bot.place_market_order(symbol, side, quantity)
            
            print("✓ Market order placed successfully!")
            print(f"Order ID: {order.get('orderId')}")
            print(f"Status: {order.get('status')}")
            print(f"Executed Quantity: {order.get('executedQty')}")
            print(f"Cumulative Quote Quantity: {order.get('cummulativeQuoteQty')}")
            
        except Exception as e:
            print(f"Error placing market order: {e}")
    
    def handle_limit_order(self):
        """Handle limit order placement"""
        try:
            print("\n--- Place Limit Order ---")
            symbol = self.get_user_input("Enter symbol (e.g., BTCUSDT)")
            side = self.get_user_input("Enter side (BUY/SELL)").upper()
            quantity = self.get_user_input("Enter quantity", float)
            price = self.get_user_input("Enter price", float)
            
            if side not in ['BUY', 'SELL']:
                print("Error: Side must be BUY or SELL")
                return
            
            # Show current price for reference
            try:
                current_price = self.bot.get_current_price(symbol)
                print(f"Current price: {current_price}")
            except:
                pass
            
            print(f"\nPlacing limit order: {side} {quantity} {symbol} at {price}")
            order = self.bot.place_limit_order(symbol, side, quantity, price)
            
            print("✓ Limit order placed successfully!")
            print(f"Order ID: {order.get('orderId')}")
            print(f"Status: {order.get('status')}")
            print(f"Price: {order.get('price')}")
            
        except Exception as e:
            print(f"Error placing limit order: {e}")
    
    def handle_stop_limit_order(self):
        """Handle stop-limit order placement"""
        try:
            print("\n--- Place Stop-Limit Order ---")
            symbol = self.get_user_input("Enter symbol (e.g., BTCUSDT)")
            side = self.get_user_input("Enter side (BUY/SELL)").upper()
            quantity = self.get_user_input("Enter quantity", float)
            price = self.get_user_input("Enter limit price", float)
            stop_price = self.get_user_input("Enter stop price", float)
            
            if side not in ['BUY', 'SELL']:
                print("Error: Side must be BUY or SELL")
                return
            
            # Show current price for reference
            try:
                current_price = self.bot.get_current_price(symbol)
                print(f"Current price: {current_price}")
            except:
                pass
            
            print(f"\nPlacing stop-limit order: {side} {quantity} {symbol} at {price}, stop: {stop_price}")
            order = self.bot.place_stop_limit_order(symbol, side, quantity, price, stop_price)
            
            print("✓ Stop-limit order placed successfully!")
            print(f"Order ID: {order.get('orderId')}")
            print(f"Status: {order.get('status')}")
            print(f"Limit Price: {order.get('price')}")
            print(f"Stop Price: {order.get('stopPrice')}")
            
        except Exception as e:
            print(f"Error placing stop-limit order: {e}")
    
    def handle_open_orders(self):
        """Handle open orders display"""
        try:
            print("\n--- Open Orders ---")
            symbol = input("Enter symbol (optional, press Enter for all): ").strip() or None
            
            orders = self.bot.get_open_orders(symbol)
            
            if not orders:
                print("No open orders found")
                return
            
            print(f"\nFound {len(orders)} open orders:")
            for order in orders:
                print(f"Order ID: {order.get('orderId')}")
                print(f"Symbol: {order.get('symbol')}")
                print(f"Side: {order.get('side')}")
                print(f"Type: {order.get('type')}")
                print(f"Quantity: {order.get('origQty')}")
                print(f"Price: {order.get('price')}")
                print(f"Status: {order.get('status')}")
                print("-" * 30)
                
        except Exception as e:
            print(f"Error getting open orders: {e}")
    
    def handle_cancel_order(self):
        """Handle order cancellation"""
        try:
            print("\n--- Cancel Order ---")
            symbol = self.get_user_input("Enter symbol (e.g., BTCUSDT)")
            order_id = self.get_user_input("Enter order ID", int)
            
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
            symbol = self.get_user_input("Enter symbol (e.g., BTCUSDT)")
            order_id = self.get_user_input("Enter order ID", int)
            
            order = self.bot.get_order_status(symbol, order_id)
            
            print(f"\nOrder Status for ID {order_id}:")
            print(f"Symbol: {order.get('symbol')}")
            print(f"Side: {order.get('side')}")
            print(f"Type: {order.get('type')}")
            print(f"Status: {order.get('status')}")
            print(f"Original Quantity: {order.get('origQty')}")
            print(f"Executed Quantity: {order.get('executedQty')}")
            print(f"Price: {order.get('price')}")
            print(f"Average Price: {order.get('avgPrice')}")
            print(f"Time: {datetime.fromtimestamp(order.get('time', 0) / 1000)}")
            
        except Exception as e:
            print(f"Error getting order status: {e}")
    
    def show_log_location(self):
        """Show log files location"""
        logs_dir = os.path.abspath('logs')
        print(f"\nLog files are stored in: {logs_dir}")
        
        if os.path.exists(logs_dir):
            log_files = [f for f in os.listdir(logs_dir) if f.endswith('.log')]
            if log_files:
                print(f"Current log files ({len(log_files)}):")
                for log_file in sorted(log_files):
                    print(f"  - {log_file}")
            else:
                print("No log files found")
        else:
            print("Logs directory does not exist yet")
    
    def run(self):
        """Run the CLI interface"""
        if not self.initialize_bot():
            return
        
        while True:
            try:
                self.display_menu()
                choice = input("\nEnter your choice (0-9): ").strip()
                
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
                    self.handle_stop_limit_order()
                elif choice == '6':
                    self.handle_open_orders()
                elif choice == '7':
                    self.handle_cancel_order()
                elif choice == '8':
                    self.handle_order_status()
                elif choice == '9':
                    self.show_log_location()
                else:
                    print("Invalid choice. Please try again.")
                
                input("\nPress Enter to continue...")
                
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                self.logger.error(f"CLI error: {e}")


def main():
    """Main function to run the trading bot"""
    parser = argparse.ArgumentParser(description='Binance Futures Trading Bot')
    parser.add_argument('--cli', action='store_true', help='Run with CLI interface')
    parser.add_argument('--api-key', help='Binance API Key')
    parser.add_argument('--api-secret', help='Binance API Secret')
    
    args = parser.parse_args()
    
    if args.cli or (not args.api_key or not args.api_secret):
        # Run CLI interface
        cli = TradingBotCLI()
        cli.run()
    else:
        # Run programmatically
        try:
            bot = BasicBot(args.api_key, args.api_secret, testnet=True)
            print("Bot initialized successfully!")
            
            # Example usage
            account_info = bot.get_account_info()
            print(f"Account Balance: {account_info.get('totalWalletBalance', 'N/A')} USDT")
            
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()