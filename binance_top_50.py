from binance.client import Client
import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import shutil

def get_top_50_futures_crypto():
    # 加载环境变量
    load_dotenv()
    
    # 从环境变量获取API密钥
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    # 初始化币安客户端
    client = Client(api_key, api_secret) if api_key and api_secret else Client()
    
    # 获取所有U本位合约信息
    futures_exchange_info = client.futures_exchange_info()
    
    # 获取所有支持合约的USDT交易对及其最大杠杆
    futures_symbols = {}
    for symbol_info in futures_exchange_info['symbols']:
        if symbol_info['symbol'].endswith('USDT') and symbol_info['status'] == 'TRADING':
            symbol = symbol_info['symbol']
            # 如果有API密钥，尝试获取实际的最大杠杆
            try:
                if api_key and api_secret:
                    leverage_info = client.futures_leverage_bracket(symbol=symbol)
                    max_leverage = max([bracket['initialLeverage'] for bracket in leverage_info[0]['brackets']])
                else:
                    max_leverage = 20  # 默认值
            except Exception:
                max_leverage = 20  # 如果获取失败，使用默认值
            futures_symbols[symbol] = max_leverage
    
    # 获取24小时行情数据
    tickers = client.get_ticker()
    
    # 转换为DataFrame
    df = pd.DataFrame(tickers)
    
    # 只保留USDT交易对且在合约列表中的币对
    df = df[df['symbol'].str.endswith('USDT')]
    df = df[df['symbol'].isin(futures_symbols.keys())]
    
    # 排除比特币和USDC
    df = df[~df['symbol'].str.startswith('BTC')]
    df = df[~df['symbol'].str.startswith('USDC')]
    
    # 计算市值（价格 * 流通量）
    df['marketCap'] = df['lastPrice'].astype(float) * df['volume'].astype(float)
    
    # 添加最大杠杆列
    df['maxLeverage'] = df['symbol'].map(futures_symbols)
    
    # 按市值排序并获取前50个
    top_50 = df.nlargest(50, 'marketCap')[['symbol', 'lastPrice', 'volume', 'marketCap', 'maxLeverage']]
    
    # 格式化输出
    top_50['lastPrice'] = top_50['lastPrice'].astype(float).round(4)
    top_50['volume'] = top_50['volume'].astype(float).round(2)
    top_50['marketCap'] = top_50['marketCap'].astype(float).round(2)
    
    # 保存交易对记录
    save_trading_pairs(top_50)
    
    return top_50

def save_trading_pairs(df):
    """保存交易对信息到JSON文件"""
    # 创建交易对记录目录
    os.makedirs('trading_pairs', exist_ok=True)
    
    # 生成带时间戳的文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    history_filename = f'trading_pairs/top_50_pairs_{timestamp}.json'
    
    # 保存历史记录
    pairs_data = df.to_dict(orient='records')
    with open(history_filename, 'w', encoding='utf-8') as f:
        json.dump(pairs_data, f, ensure_ascii=False, indent=2)
    
    # 保存最新记录到固定文件
    latest_filename = 'trading_pairs/latest_pairs.json'
    with open(latest_filename, 'w', encoding='utf-8') as f:
        json.dump(pairs_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n交易对记录已保存到: {history_filename}")
    print(f"最新交易对记录已保存到: {latest_filename}")

if __name__ == "__main__":
    try:
        print("获取币安U本位合约市值前50的加密货币（不含BTC和USDC）...")
        top_50 = get_top_50_futures_crypto()
        print("\n市值前50的加密货币（按市值排序）：")
        print(top_50.to_string(index=False))
        
        # 检查是否使用了API密钥
        if not (os.getenv('BINANCE_API_KEY') and os.getenv('BINANCE_API_SECRET')):
            print("\n注意：未检测到API密钥，显示的是默认杠杆倍数20倍。要获取准确的杠杆倍数，请在.env文件中配置API密钥。")
    except Exception as e:
        print(f"发生错误: {str(e)}") 