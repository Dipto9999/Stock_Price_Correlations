#######################
### Import Modules. ###
#######################

from market import Market

import datetime as dt

import pandas as pd
import pandas_datareader as web
import sqlite3

import matplotlib.pyplot as plt
import seaborn as sns

from IPython.display import display

#################
### Portfolio ###
#################

class Portfolio() :
    def __init__(self, tickers, days) :
        # Connect To Database.
        con = sqlite3.connect('stock_trades.db')
        # Create Cursor.
        c = con.cursor()

        # Check If Tables Exist.
        statement = ''' SELECT COUNT(*) FROM sqlite_master WHERE TYPE = 'table' AND NAME = 'holdings' '''
        c.execute(statement)
        found = pd.DataFrame(c.fetchall())[0][0]

        statement = ''' SELECT COUNT(*) FROM sqlite_master WHERE TYPE = 'table' AND NAME = 'balances' '''
        c.execute(statement)
        found &= pd.DataFrame(c.fetchall())[0][0]

        # Close Connection.
        con.close()

        # Table Does Not Exist.
        if (found == 0) :
            self.tickers = tickers
            start = dt.datetime.today() - dt.timedelta(days)
            # today().date()
            effective_dates = []
            for number_days in range((dt.datetime.today().date() - start.date()).days) :
                effective_dates.append((start + dt.timedelta(number_days)).date())

            self.holdings = pd.DataFrame(columns = tickers, index = effective_dates).fillna(0)
            self.holdings.index.name = 'Date'

            self.balances = {}
            for ticker in self.tickers :
                self.balances[ticker] = 0

            self.__set_holdings()
            self.__set_balances()

        # Table Exists.
        else :
            self.get_tickers()
            self.get_holdings()

            delta = dt.datetime.today().date() - self.holdings.index[-1]
            effective_dates = [self.holdings.index[-1] + dt.timedelta(days = (i + 1)) for i in range(delta.days + 1)]

            # Duplicate Most Recent Purchase Activity.
            updated_holdings = pd.DataFrame(index = effective_dates, columns = self.holdings.columns)
            for i, row in updated_holdings.iterrows() :
                updated_holdings.loc[i] = self.holdings.iloc[-1:].values

            self.holdings = pd.concat(
                [self.holdings, updated_holdings],
                ignore_index = False
            )

            self.holdings.index.name = 'Date'

            self.get_balances()

        self.__set_holdings()

    def __del__(self) :
        # Connect To Database.
        con = sqlite3.connect('stock_trades.db')
        # Create Cursor.
        c = con.cursor()

        # Drop holdings Table.
        statement = ''' DROP TABLE IF EXISTS holdings '''
        c.execute(statement)

        # Drop Balances Table.
        statement = ''' DROP TABLE IF EXISTS balances '''
        c.execute(statement)

        # Close Connection.
        con.close()

    def get_tickers(self) :
        # Connect To Database.
        con = sqlite3.connect('stock_trades.db')
        # Create Cursor.
        c = con.cursor()

        # Retrieve Table Column Names.
        statement = ''' PRAGMA table_info(holdings) '''
        c.execute(statement)

        columns_df = pd.DataFrame(
            data = c.fetchall(),
            columns = ['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk']
        )

        # Close Connection.
        con.close()

        self.tickers = columns_df['name'][columns_df['name'] != 'Date'].to_list()

        return self.tickers

    def get_holdings(self) :
        # Connect To Database.
        con = sqlite3.connect('stock_trades.db')
        # Create Cursor.
        c = con.cursor()

        # Retrieve Table Data.
        statement = ''' SELECT * FROM holdings '''
        c.execute(statement)

        self.holdings = pd.DataFrame(data = c.fetchall(), columns = ['Date'] + self.tickers)

        # Close Connection.
        con.close()

        self.holdings['Date'] = self.holdings['Date'].map(lambda x : dt.datetime.strptime(x, '%Y-%m-%d').date())
        self.holdings.set_index(keys = self.holdings['Date'], inplace = True)
        self.holdings.drop(columns = ['Date'], inplace = True)

        return self.holdings

    def get_balances(self) :
        # Connect To Database.
        con = sqlite3.connect('stock_trades.db')
        # Create Cursor.
        c = con.cursor()

        statement = ''' SELECT * FROM balances '''
        c.execute(statement)

        self.balances = pd.DataFrame(data = c.fetchall(), columns = self.tickers)
        self.balances = self.balances.to_dict(orient = 'records')[0]

        # Close Connection.
        con.close()

        return self.balances

    def __set_holdings(self) :
        # Connect To Database.
        con = sqlite3.connect('stock_trades.db')
        # Create Cursor.
        c = con.cursor()

        self.holdings.to_sql(
            name = 'holdings',
            con = con,
            if_exists = 'replace',
            index = True,
        )

        # Close Connection.
        con.close()

    def __set_balances(self) :
        # Connect To Database.
        con = sqlite3.connect('stock_trades.db')
        # Create Cursor.
        c = con.cursor()

        balances_df = pd.DataFrame(columns = self.balances.keys())
        balances_df.loc[0] = self.balances.values()

        balances_df.to_sql(
            name = 'balances',
            con = con,
            if_exists = 'replace',
            index = False,
        )

        # Close Connection.
        con.close()

    def buy_stock(self, ticker, shares, adj_closes, date) :
        for current, row in self.holdings.iterrows() :
            difference = (current - date).days

            if difference >= 0 :
                row[ticker] += shares
        print(adj_closes)
        self.balances[ticker] += shares * float(adj_closes.at[date, ticker])

        self.__set_holdings()
        self.__set_balances()

    def sell_stock(self, ticker, shares, adj_closes, date) :
        sold = self.holdings.at[date, ticker] >= shares

        for current, row in self.holdings.iterrows() :
            difference = (current - date).days

            if difference >= 0 :
                sold &= row[ticker] >= shares

        if (not sold) :
            return 0

        for current, row in self.holdings.iterrows() :
            difference = (current - date).days

            if difference >= 0 :
                row[ticker] -= shares

        print(self.holdings)

        liquidated = shares * float(adj_closes.at[date, ticker])
        self.balances[ticker] = round(self.holdings.at[date, ticker] * self.balances[ticker]/(shares + self.holdings.at[date, ticker]), 2)

        self.__set_holdings()
        self.__set_balances()

        return liquidated

    def add_ticker(self, new_ticker) :
        self.tickers.append(new_ticker)
        self.holdings[new_ticker] = [0 for i in range(len(self.holdings.index))]
        self.__set_holdings()

        self.balances[new_ticker] = 0
        self.__set_balances()

    def __calculate_balance(self, adj_closes, effective_holdings, date) :
        current = 0
        for ticker in effective_holdings.columns :
            current += float(effective_holdings.at[date, ticker]) * float(adj_closes.at[date, ticker])
        return round(current, 2)

    def calculate_balances(self, adj_closes, date) :
        current_balances = {}
        for ticker in self.holdings.columns :
            current_balance = self.__calculate_balance(
                adj_closes = adj_closes,
                effective_holdings = self.holdings[ticker].to_frame(),
                date = date
            )
            if current_balance > 0 :
                current_balances[ticker] = current_balance
        return current_balances

    def __calculate_profit(self, adj_closes, starting_balance, effective_holdings, date) :
        return round((self.__calculate_balance(adj_closes, effective_holdings, date) - starting_balance), 2)

    def calculate_profits(self, adj_closes, date) :
        profits = {}
        current_balances = self.calculate_balances(adj_closes, date)
        for ticker in current_balances.keys() :
            profits[ticker] = self.__calculate_profit(
                adj_closes = adj_closes,
                starting_balance = self.balances[ticker],
                effective_holdings = self.holdings[ticker].to_frame(),
                date = date
            )
        return profits

    def display_portfolio(self, adj_closes) :
        last_close = adj_closes.index[-1]

        current_balances = self.calculate_balances(adj_closes = adj_closes, date = last_close)
        profits = self.calculate_profits(adj_closes = adj_closes, date = last_close)

        fig, ax = plt.subplots(figsize = (16, 8))
        fig.patch.set_facecolor('#a9a9a9')
        ax.set_title('Stock Portfolio', color = 'white', fontweight = 'bold', size = 20)

        ax.tick_params(axis = 'x', color = 'white')
        ax.tick_params(axis = 'y', color = 'white')

        wedges, texts, autotexts = ax.pie(
            current_balances.values(),
            labels = current_balances.keys(),
            textprops = dict(color = 'black'),
            autopct = '%1.1f%%',
            pctdistance = 0.8
        )

        [text.set_color('white') for text in texts]

        plt.setp(texts, size = 10, weight = 'bold')
        plt.setp(autotexts, size = 10, weight = 'bold')

        chart_center = plt.Circle((0, 0), 0.45, color = 'black')
        plt.gca().add_artist(chart_center)

        # Portfolio Preview Label

        ax.text(
            x = -2, y = 1,
            s = 'Portfolio Preview',
            fontsize = 14,
            fontweight = 'bold',
            color = 'white',
            verticalalignment = 'center',
            horizontalalignment = 'center'
        )

        # Current Balances

        ax.text(
            x = -2, y = 0.85,
            s = f'Total Value : {sum(current_balances.values()):.2f} USD',
            fontsize = 12,
            fontweight = 'semibold',
            color = 'white',
            verticalalignment = 'center',
            horizontalalignment = 'center'
        )

        # Profits

        offset = -0.15
        for ticker, profit in profits.items() :
            if profit > 0 :
                profit_display = f'{ticker} : +{profit:.2f} USD'
                text_color = 'green'
            if profit < 0 :
                profit_display = f'{ticker} : {profit:.2f} USD'
                text_color = 'red'
            if profit == 0 :
                profit_display = f'{ticker} : {profit:.2f} USD'
                text_color = 'white'
            ax.text(
                x = -2, y = 0.85 + offset,
                s = profit_display,
                fontsize = 12,
                fontweight = 'semibold',
                color = text_color,
                verticalalignment = 'center',
                horizontalalignment = 'center'
            )
            offset -= 0.15

        plt.show()
        plt.rcdefaults()

def test_portfolio() :
    market = Market(
        tickers = ['TSLA', 'MSFT', 'AAPL', 'FB', 'NVDA', 'AMD', 'QCOM', 'CLVS'],
        days = 365
    )

    portfolio = Portfolio(
        tickers = ['TSLA', 'MSFT', 'AAPL', 'FB', 'NVDA', 'AMD', 'QCOM', 'CLVS'],
        days = 365
    )

    portfolio.buy_stock(
        ticker = 'AAPL',
        shares = 14,
        adj_closes = market.get_adjcloses(),
        date = dt.date(2022, 2, 18)
    )

    portfolio.buy_stock(
        ticker = 'CLVS',
        shares = 1352,
        adj_closes = market.get_adjcloses(),
        date = dt.date(2022, 2, 18),
    )

    portfolio.buy_stock(
        ticker = 'AAPL',
        shares = 4,
        adj_closes = market.get_adjcloses(),
        date = dt.date(2022, 2, 24)
    )

    portfolio.buy_stock(
        ticker = 'CLVS',
        shares = 415,
        adj_closes = market.get_adjcloses(),
        date = dt.date(2022, 2, 25)
    )

    portfolio.buy_stock(
        ticker = 'AAPL',
        shares = 5,
        adj_closes = market.get_adjcloses(),
        date = dt.date(2022, 3, 14),
    )

    portfolio.display_portfolio(adj_closes = market.get_adjcloses())

    revenue = portfolio.sell_stock(
        ticker = 'CLVS',
        shares = 1500,
        adj_closes = market.get_adjcloses(),
        date = dt.date(2022, 4, 6)
    )
    print(revenue)

    portfolio.display_portfolio(market.get_adjcloses())

    market.add_ticker('WMT')
    portfolio.add_ticker('WMT')

    portfolio.buy_stock(
        ticker = 'WMT',
        shares = 5,
        adj_closes = market.get_adjcloses(),
        date = dt.date(2022, 3, 14)
    )

    revenue = portfolio.sell_stock(
        ticker = 'WMT',
        shares = 5,
        adj_closes = market.get_adjcloses(),
        date = dt.date(2022, 2, 7)
    )
    print(revenue)

    portfolio.display_portfolio(adj_closes = market.get_adjcloses())

    del portfolio
