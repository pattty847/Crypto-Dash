from collections import defaultdict
from typing import List

import pandas as pd
from tabulate import tabulate

from src.data.influx import InfluxDB
from src.gui.signals import SignalEmitter


class MarketAggregator:
    def __init__(self, influx: InfluxDB, emitter: SignalEmitter):
        self.emitter = emitter
        self.trade_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        self.order_size_categories = [
            "0-10k",
            "10k-100k",
            "100k-1m",
            "1m-10m",
            "10m-100m",
        ]
        self.influx = influx


    def calc_trade_stats(self, exchange: str, trades: List[str]) -> None:
        """
        The calc_trade_stats function will be passed a particular exchange and tick data (containing the symbol, and other relevant information).
        It will then calculate the following metrics:
            - Total volume for an exchange and symbol pair
            - Total volume in USD for an exchange and symbol pair
        
        :param self: Reference the object that is calling the function
        :param exchange: str: Specify the exchange that the trade data is coming from
        :param trades: List[str]: Pass in the tick data
        :return: A tuple containing the symbol and trade_stats dictionary
        self.trade_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        = {
            ('exchange1', 'symbol1'): {
                'category1': {
                    'metric1': 0.0,
                    'metric2': 0.0,
                    ...
                },
                'category2': {
                    'metric1': 0.0,
                    'metric2': 0.0,
                    ...
                },
                ...
            },
            ('exchange2', 'symbol2'): {
                ...
            },
            ...
        }
        :doc-author: Trelent
        """
        # This function will be passed a particular exchange and tick data (containing the symbol, and other relevant information)
        try:
            # trades = list[dict_keys(['id', 'order', 'info', 'timestamp', 'datetime', 'symbol', 'type', 'takerOrMaker', 'side', 'price', 'amount', 'fee', 'cost', 'fees'])]
            for trade in trades:
                symbol = trade["symbol"]
                # Check if necessary fields are in the trade data
                if not all(key in trade for key in ("price", "amount", "side")):
                    print(f"Trade data is missing necessary fields: {trade}")
                    return

                # Convert amount to float once and store the result
                try:
                    amount = float(trade["amount"])  # base currency
                except ValueError:
                    print(f"Amount is not a number: {trade['amount']}")
                    return

                # Check if side is either "buy" or "sell"
                if trade["side"] not in ("buy", "sell"):
                    print(f"Invalid trade side: {trade['side']}")
                    return

                order_cost = float(trade["price"]) * amount  # quote currency
                order_size_category = self.get_order_size_category_(order_cost)

                # Total volume for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]["volume"]["total_base"] += amount

                # Total volume in USD for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]["volume"][
                    "total_usd"
                ] += order_cost

                # CVD for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]["CVD"]["total_base"] += (
                    amount if trade["side"] == "buy" else -amount
                )
                self.trade_stats[(exchange, symbol)]["CVD"]["total_usd"] += (
                    amount * trade["price"]
                    if trade["side"] == "buy"
                    else -amount * trade["price"]
                )

                # CVD and Volume for an order size separated into categories based on size, for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]["CVD"][order_size_category] += (
                    amount if trade["side"] == "buy" else -amount
                )
                self.trade_stats[(exchange, symbol)]["volume"][
                    order_size_category
                ] += amount

                return symbol, self.trade_stats[(exchange, symbol)]

        except Exception as e:
            print(f"Error processing trade data: {e}")


    def get_order_size_category_(self, order_cost):
        if order_cost < 1e4:
            return "0-10k"
        elif order_cost < 1e5:
            return "10k-100k"
        elif order_cost < 1e6:
            return "100k-1m"
        elif order_cost < 1e7:
            return "1m-10m"
        elif order_cost < 1e8:
            return "10m-100m"


    def report_statistics(self):
        header = [
            "Exchange/Symbol",
            "USD Vol",
            "Base Vol",
            "Delta USD",
            "Delta BASE",
            "0-10k",
            "0-10kΔ",
            "10k-100k",
            "10k-100kΔ",
            "100k-1m",
            "100k-1mΔ",
            "1m-10m",
            "1m-10mΔ",
            "10m-100m",
            "10m-100mΔ",
        ]

        rows = []
        for (exchange, symbol), values in self.trade_stats.items():
            row = [
                f"{exchange}: {symbol}",
                f"{values['volume']['total_usd']:.2f}",  # Volume for USD
                f"{values['volume']['total_base']:.4f}",  # Volume for BASE
                f"{values['CVD']['total_usd']:.4f}",  # CVD for BASE
                f"{values['CVD']['total_base']:.4f}",
            ]  # CVD for USD

            for category in self.order_size_categories:
                row.append(f"{values['volume'][category]:.4f}")  # Volume for category
                row.append(f"{values['CVD'][category]:.4f}")  # Delta for category

            rows.append(row)

        print(tabulate(rows, headers=header, tablefmt="grid"))
        # print(self.trade_stats)


    def on_order_book_update(self, exchange, orderbook, tick_size, aggregate, ob_levels):

        # Extract bids and asks
        bids = orderbook['bids']
        asks = orderbook['asks']

        if aggregate:
            # Process for aggregated view
            bids_df = self.group_and_aggregate(bids, tick_size)
            asks_df = self.group_and_aggregate(asks, tick_size)
            price_column = 'price_group'
        else:
            # Process for non-aggregated view
            bids_df = pd.DataFrame(bids, columns=['price', 'quantity'])
            asks_df = pd.DataFrame(asks, columns=['price', 'quantity'])
            price_column = 'price'

        # Sorting and calculations
        bids_df = bids_df.sort_values(by=price_column, ascending=False).head(ob_levels)
        asks_df = asks_df.sort_values(by=price_column, ascending=True).head(ob_levels)
        bids_df['cumulative_quantity'] = bids_df['quantity'].cumsum()
        asks_df['cumulative_quantity'] = asks_df['quantity'].cumsum()

        # Update the series data
        return bids_df, asks_df, price_column
    

    def group_and_aggregate(self, orders, tick_size):
        df = pd.DataFrame(orders, columns=['price', 'quantity'])
        df['price_group'] = (df['price'] // tick_size) * tick_size
        return df.groupby('price_group').agg({'quantity': 'sum'}).reset_index()
    
    
    def resample_data(self, ohlcv: pd.DataFrame, timeframe_str):
        temp_ohlcv = ohlcv.copy()
        temp_ohlcv['dates'] = pd.to_datetime(temp_ohlcv['dates'], unit='s')
        temp_ohlcv.set_index('dates', inplace=True)

        if timeframe_str.endswith('m'):
            timeframe_str = timeframe_str.replace('m', 'T')
        resampled_ohlcv = self.perform_resampling(temp_ohlcv, timeframe_str)

        return resampled_ohlcv
    

    def perform_resampling(self, data, timeframe):
        # Perform the actual resampling
        resampled_ohlcv = data.resample(timeframe).agg({
            'opens': 'first',
            'highs': 'max',
            'lows': 'min',
            'closes': 'last',
            'volumes': 'sum'
        }).dropna().reset_index()

        resampled_ohlcv['dates'] = resampled_ohlcv['dates'].view('int64') // 1e9
        return resampled_ohlcv.reset_index(drop=True)