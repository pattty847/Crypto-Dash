import dearpygui.dearpygui as dpg

from src.config import ConfigManager
from src.data.data_source import Data
from src.gui.signals import SignalEmitter, Signals


class OrderBook:
    def __init__(self, emitter: SignalEmitter, data: Data, config: ConfigManager):
        self.emitter = emitter
        self.data = data
        self.config = config
    

        self.orderbook_tag = None
        self.show_orderbook = True
        self.aggregated_order_book = True
        self.order_book_levels = 100
        self.tick_size = 10 # TODO: This needs to be dynamic based on the symbols precision 
        
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self.on_order_book_update)

    def setup_orderbook_menu(self):
        with dpg.menu(label="Orderbook"):
            dpg.add_checkbox(label="Show", default_value=self.show_orderbook, callback=self.toggle_orderbook)
    
    def toggle_orderbook(self):
        self.show_orderbook = not self.show_orderbook
        if self.show_orderbook:
            dpg.configure_item("order_book_group", show=self.show_orderbook)
            dpg.configure_item("charts_group", width=dpg.get_viewport_width() * 0.7)
        else:
            dpg.configure_item("charts_group", width=-1)

    def create_order_book_ui(self):
        dpg.add_checkbox(label="Aggregate", default_value=self.aggregated_order_book, callback=self.toggle_aggregated_order_book)
        dpg.add_slider_int(label="Levels", default_value=self.order_book_levels, min_value=5, max_value=1000, callback=self.set_ob_levels)
        with dpg.plot(label="Orderbook", no_title=True, height=-1) as self.orderbook_tag:
            dpg.add_plot_legend()
            self.ob_xaxis = dpg.add_plot_axis(dpg.mvXAxis)
            with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.ob_yaxis:
                self.bids_tag = dpg.add_line_series([], [])
                self.asks_tag = dpg.add_line_series([], [])

    # Rest of the methods related to order book (update_order_book, set_ob_levels, etc.)

    def on_order_book_update(self, exchange, orderbook):
        bids_df, ask_df, price_column = self.data.agg.on_order_book_update(exchange, orderbook, self.tick_size, self.aggregated_order_book, self.order_book_levels)
        self.update_order_book(bids_df, ask_df, price_column)
    
    def update_order_book(self, bids_df, asks_df, price_column):
        dpg.configure_item(self.bids_tag, x=bids_df[price_column].tolist(), y=bids_df['cumulative_quantity'].tolist())
        dpg.configure_item(self.asks_tag, x=asks_df[price_column].tolist(), y=asks_df['cumulative_quantity'].tolist())
        
        # Find the range for price and quantity
        min_price = min(bids_df[price_column].min(), asks_df[price_column].min())
        max_price = max(bids_df[price_column].max(), asks_df[price_column].max())
        max_quantity = max(bids_df['cumulative_quantity'].max(), asks_df['cumulative_quantity'].max())

        # Update the x-axis limits for price
        dpg.set_axis_limits(axis=self.ob_xaxis, ymin=min_price, ymax=max_price)

        # Update the y-axis limits for quantity
        dpg.set_axis_limits(axis=self.ob_yaxis, ymin=0, ymax=max_quantity)

    
    def toggle_aggregated_order_book(self):
        self.aggregated_order_book = not self.aggregated_order_book
                            
    def set_ob_levels(self, levels):
        self.order_book_levels = levels