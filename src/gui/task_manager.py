import asyncio
import logging
import threading

from src.data.data_source import Data
from src.gui.utils import calculate_since

class TaskManager:
    def __init__(self, data: Data):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.tasks = {}
        self.data = data
        self.active_symbol = None

    def run_loop(self):
        logging.info(f'Starting async thread.')
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_task(self, name: str, coro):
        logging.info(f"Starting new task {name}")
        task = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks[name] = task
        task.add_done_callback(lambda t: self.tasks.pop(name, None))
        
    def start_stream(self, exchange, symbol, timeframe, cant_resample: bool):
        
        if self.active_symbol != None and self.active_symbol != symbol:
            self.stop_all_tasks()

        if cant_resample:
            if f"trades_{symbol}" in self.tasks:
                self.stop_task(f"trades_{symbol}")


        since = calculate_since(self.data.exchange_list[exchange]['ccxt'], timeframe, 365)
        # We need to fetch the candles (wait for them), this emits 'Signals.NEW_CANDLES', func 'on_new_candles' should set them    
        self.run_task_until_complete(self.data.fetch_candles(exchanges=[exchange], symbols=[symbol], timeframes=[timeframe], since=since, write_to_db=False))
        
        if f"trades_{symbol}" not in self.tasks:
            # We start the stream (ticks), this emits 'Signals.NEW_TRADE', func 'on_new_trade' handles building of candles
            self.start_task(
                f'trades_{symbol}', 
                # TODO: Add 'exchange' parameter to 'stream_trades'
                coro=self.data.watch_trades(
                    symbols=[symbol], 
                    track_stats=True
                )
            )
        
        if f"orderbook_{symbol}" not in self.tasks:
            self.start_task(
                f'orderbook_{symbol}', 
                # TODO: Add 'exchange' parameter to 'stream_trades'
                coro=self.data.watch_orderbook(
                    symbols=[symbol], 
                )
            )
            
        self.active_symbol = symbol
        
    def run_task_until_complete(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result()
        except asyncio.CancelledError:
            logging.error("Task was cancelled.")
            # Handle task cancellation, if needed
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            # Handle other exceptions

    def stop_task(self, name: str):
        if name in self.tasks:
            logging.info(f"Stopping task {name}")
            self.tasks[name].cancel()

    def stop_all_tasks(self):
        if not self.tasks:
            return
        logging.info(f'Stopping all async tasks: {list(self.tasks.keys())}')
        tasks_copy = dict(self.tasks)  # Create a copy of the dictionary
        for task in tasks_copy.values():
            task.cancel()
        self.tasks.clear()