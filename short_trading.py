from binance.client import Client
from binance.enums import *
import pandas as pd
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from trading_config import TRADING_CONFIG
import math
import time

class ShortTrader:
    def __init__(self):
        # 加载环境变量
        load_dotenv()
        
        # 从环境变量获取API密钥
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')
        
        if not api_key or not api_secret:
            raise ValueError("请在.env文件中设置BINANCE_API_KEY和BINANCE_API_SECRET")
        
        # 初始化币安客户端
        self.client = Client(api_key, api_secret)
        
        # 设置持仓模式为双向持仓
        try:
            self.client.futures_change_position_mode(dualSidePosition=True)
            print("已设置为双向持仓模式")
        except Exception as e:
            print(f"设置双向持仓模式时出错（可能已经是双向持仓）: {str(e)}")
        
        # 加载配置
        self.config = TRADING_CONFIG
        
        # 加载交易对
        self.load_trading_pairs()
        
        # 获取交易对信息
        self.exchange_info = self.client.futures_exchange_info()
    
    def load_trading_pairs(self):
        """加载交易对信息"""
        try:
            with open(self.config['pairs_file'], 'r') as f:
                self.pairs = json.load(f)
            print(f"成功加载 {len(self.pairs)} 个交易对")
        except Exception as e:
            raise Exception(f"加载交易对文件失败: {str(e)}")
    
    def get_quantity_precision(self, symbol):
        """获取交易对的数量精度"""
        for symbol_info in self.exchange_info['symbols']:
            if symbol_info['symbol'] == symbol:
                for filter in symbol_info['filters']:
                    if filter['filterType'] == 'LOT_SIZE':
                        step_size = float(filter['stepSize'])
                        precision = int(round(-math.log10(step_size)))
                        return precision
        return 8  # 默认精度
    
    def calculate_position_size(self, symbol, current_price):
        """计算仓位大小"""
        try:
            if current_price <= 0:
                print(f"跳过 {symbol}: 价格无效 ({current_price})")
                return 0
                
            capital = self.config['capital_per_coin']
            leverage = self.config['leverage']
            position_size = (capital * leverage) / current_price
            
            # 获取数量精度
            precision = self.get_quantity_precision(symbol)
            
            # 根据精度截断数量
            position_size = float(format(position_size, f'.{precision}f'))
            
            return position_size
        except Exception as e:
            print(f"计算 {symbol} 仓位大小时出错: {str(e)}")
            return 0
    
    def place_short_order(self, symbol, position_size, current_price):
        """下做空订单"""
        try:
            # 检查价格是否有效
            if current_price <= 0:
                print(f"跳过 {symbol}: 价格无效 ({current_price})")
                return None
                
            # 设置杠杆
            self.client.futures_change_leverage(
                symbol=symbol,
                leverage=self.config['leverage']
            )
            
            # 设置全仓模式
            try:
                self.client.futures_change_margin_type(
                    symbol=symbol,
                    marginType='CROSSED'
                )
                print(f"{symbol} 已设置为全仓模式")
            except Exception as e:
                if "No need to change margin type" not in str(e):
                    print(f"{symbol} 设置全仓模式时出错: {str(e)}")
            
            # 获取价格精度
            price_precision = 0
            quantity_precision = 0
            for symbol_info in self.exchange_info['symbols']:
                if symbol_info['symbol'] == symbol:
                    for filter in symbol_info['filters']:
                        if filter['filterType'] == 'PRICE_FILTER':
                            tick_size = float(filter['tickSize'])
                            price_precision = int(round(-math.log10(tick_size)))
                        elif filter['filterType'] == 'LOT_SIZE':
                            step_size = float(filter['stepSize'])
                            quantity_precision = int(round(-math.log10(step_size)))
                    break
            
            # 获取最新价格
            try:
                ticker = self.client.futures_symbol_ticker(symbol=symbol)
                current_price = float(ticker['price'])
                print(f"{symbol} 当前价格: {current_price}")
            except Exception as e:
                print(f"错误: 获取 {symbol} 最新价格失败: {str(e)}")
                return None
            
            # 计算止损止盈价格
            stop_loss_price = current_price * (1 + self.config['stop_loss_percent'] / 100)
            take_profit_price = current_price * (1 - self.config['take_profit_percent'] / 100)
            
            # 根据精度格式化价格
            stop_loss_price = float(format(stop_loss_price, f'.{price_precision}f'))
            take_profit_price = float(format(take_profit_price, f'.{price_precision}f'))
            
            # 检查止盈止损价格是否有效
            if stop_loss_price <= current_price:
                print(f"警告: {symbol} 止损价格 {stop_loss_price} 低于当前价格 {current_price}，调整止损价格")
                stop_loss_price = current_price * 1.01  # 设置为当前价格的1%
                stop_loss_price = float(format(stop_loss_price, f'.{price_precision}f'))
            
            if take_profit_price >= current_price:
                print(f"警告: {symbol} 止盈价格 {take_profit_price} 高于当前价格 {current_price}，调整止盈价格")
                take_profit_price = current_price * 0.99  # 设置为当前价格的99%
                take_profit_price = float(format(take_profit_price, f'.{price_precision}f'))
            
            # 下做空订单
            try:
                order = self.client.futures_create_order(
                    symbol=symbol,
                    side=SIDE_SELL,
                    type=ORDER_TYPE_MARKET,
                    quantity=position_size,
                    positionSide='SHORT'
                )
                
                # 设置止损（带重试机制）
                stop_loss_success = False
                max_retries = 3
                retry_count = 0
                
                while not stop_loss_success and retry_count < max_retries:
                    try:
                        self.client.futures_create_order(
                            symbol=symbol,
                            side=SIDE_BUY,
                            type='STOP_MARKET',
                            stopPrice=stop_loss_price,
                            closePosition=True,
                            positionSide='SHORT'
                        )
                        stop_loss_success = True
                        print(f"成功为 {symbol} 设置止损价格: {stop_loss_price}")
                    except Exception as e:
                        retry_count += 1
                        if "Order would immediately trigger" in str(e):
                            print(f"警告: {symbol} 止损价格 {stop_loss_price} 已触发，尝试调整止损价格")
                            # 调整止损价格
                            stop_loss_price = current_price * (1 + (0.5 + retry_count * 0.5) / 100)
                            stop_loss_price = float(format(stop_loss_price, f'.{price_precision}f'))
                            print(f"尝试新的止损价格: {stop_loss_price}")
                        else:
                            print(f"错误: {symbol} 设置止损失败 (尝试 {retry_count}/{max_retries}): {str(e)}")
                            time.sleep(1)  # 等待1秒后重试
                
                # 设置止盈（带重试机制）
                take_profit_success = False
                retry_count = 0
                
                while not take_profit_success and retry_count < max_retries:
                    try:
                        self.client.futures_create_order(
                            symbol=symbol,
                            side=SIDE_BUY,
                            type='TAKE_PROFIT_MARKET',
                            stopPrice=take_profit_price,
                            closePosition=True,
                            positionSide='SHORT'
                        )
                        take_profit_success = True
                        print(f"成功为 {symbol} 设置止盈价格: {take_profit_price}")
                    except Exception as e:
                        retry_count += 1
                        if "Order would immediately trigger" in str(e):
                            print(f"警告: {symbol} 止盈价格 {take_profit_price} 已触发，尝试调整止盈价格")
                            # 调整止盈价格
                            take_profit_price = current_price * (1 - (0.5 + retry_count * 0.5) / 100)
                            take_profit_price = float(format(take_profit_price, f'.{price_precision}f'))
                            print(f"尝试新的止盈价格: {take_profit_price}")
                        else:
                            print(f"错误: {symbol} 设置止盈失败 (尝试 {retry_count}/{max_retries}): {str(e)}")
                            time.sleep(1)  # 等待1秒后重试
                
                # 检查是否成功设置了止盈止损
                if stop_loss_success and take_profit_success:
                    print(f"成功下做空订单: {symbol}")
                    print(f"仓位大小: {position_size}")
                    print(f"止损价格: {stop_loss_price} ({self.config['stop_loss_percent']}%)")
                    print(f"止盈价格: {take_profit_price} ({self.config['take_profit_percent']}%)")
                else:
                    print(f"警告: {symbol} 订单已开仓，但止盈止损设置不完整")
                    if not stop_loss_success:
                        print(f"  - 止损设置失败")
                    if not take_profit_success:
                        print(f"  - 止盈设置失败")
                    
                    # 如果止盈止损设置失败，尝试平仓
                    try:
                        print(f"尝试平仓 {symbol} 以避免风险")
                        self.client.futures_create_order(
                            symbol=symbol,
                            side=SIDE_BUY,
                            type=ORDER_TYPE_MARKET,
                            quantity=position_size,
                            positionSide='SHORT'
                        )
                        print(f"成功平仓 {symbol}")
                    except Exception as e:
                        print(f"错误: 平仓 {symbol} 失败: {str(e)}")
                
                return order
                
            except Exception as e:
                if "Order would immediately trigger" in str(e):
                    print(f"错误: {symbol} 当前价格已触发止损或止盈，无法开仓")
                else:
                    print(f"错误: {symbol} 下单失败: {str(e)}")
                return None
            
        except Exception as e:
            print(f"错误: 处理 {symbol} 时出错: {str(e)}")
            return None
    
    def start_trading(self):
        """开始交易"""
        if not self.config['enable_auto_trade']:
            print("自动交易未启用，请在配置文件中设置 enable_auto_trade = True")
            return
        
        # 检查合约账户余额
        account = self.client.futures_account()
        available_balance = float(account['availableBalance'])
        print(f"\n当前合约账户可用余额: {available_balance:.2f} USDT")
        
        if available_balance < self.config['initial_capital']:
            print(f"错误：合约账户可用余额不足！需要 {self.config['initial_capital']} USDT，当前只有 {available_balance:.2f} USDT")
            print("请先手动划转足够的USDT到合约账户")
            return
        
        print("\n开始做空交易...")
        print(f"初始资金: {self.config['initial_capital']} USDT")
        print(f"每个币种分配: {self.config['capital_per_coin']} USDT")
        print(f"杠杆倍数: {self.config['leverage']}x")
        print(f"止损比例: {self.config['stop_loss_percent']}%")
        print(f"止盈比例: {self.config['take_profit_percent']}%")
        print("交易模式: 全仓")
        
        print(f"\n准备交易 {len(self.pairs)} 个交易对")
        print("交易对列表：")
        for pair in self.pairs:
            print(f"- {pair['symbol']}")
        print()
        
        for pair in self.pairs:
            symbol = pair['symbol']
            current_price = float(pair['lastPrice'])
            
            # 计算仓位大小
            position_size = self.calculate_position_size(symbol, current_price)
            
            # 下做空订单
            if self.config['enable_short']:
                self.place_short_order(symbol, position_size, current_price)
            
            # 等待0.5秒，避免触发API请求限制
            time.sleep(0.5)
        
        print("\n所有订单已下达完成")

if __name__ == "__main__":
    try:
        trader = ShortTrader()
        trader.start_trading()
    except Exception as e:
        print(f"发生错误: {str(e)}") 