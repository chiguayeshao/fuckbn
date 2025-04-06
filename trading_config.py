# 交易配置
TRADING_CONFIG = {
    # 初始资金（USDT）
    'initial_capital': 1000,
    
    # 每个币种分配的资金（USDT）
    'capital_per_coin': 20,
    
    # 杠杆倍数
    'leverage': 10,
    
    # 止损比例（百分比）
    'stop_loss_percent': 5,
    
    # 止盈比例（百分比）
    'take_profit_percent': 1,
    
    # 是否启用做空
    'enable_short': True,
    
    # 是否启用自动交易
    'enable_auto_trade': True,
    
    # 交易对文件路径（相对于当前目录）
    'pairs_file': 'trading_pairs/latest_pairs.json'
} 