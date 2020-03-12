import os
import io
import re
import lxml
import json
import requests
import numpy as np
import pandas as pd

from datetime import date
from functools import reduce
from bs4 import BeautifulSoup

####################################################
## Functions and Variables for Accessing API keys ##
####################################################

def get_api_key(source):
    """
    Returns api key for the specific source, :param source:.

    :param source: string, name of api source either 'quandl' or 'alphavantage'

    ---> String, api key for the the specific source :param source:
    """

    path_to_keys = os.path.expanduser('~/.stockanalysis_keys.json')
    with open(path_to_keys, 'r') as f:
        api_keys = json.load(f)

    return api_keys[source]

########################################################
## END Functions and Variables for Accessing API keys ##
########################################################

#################################
## Functions for fetching data ##
#################################

def fetch_stock_data(ticker, start_date, end_date, source='alphavantage'):
    """
    Returns end of day stock price DataFrame from various sources.

    :param ticker: string, stock ticker
    :param start_date: string, date to start collecting data at,
                       format: YYYY-MM-DD
    :param end_date: string, date to end collecting data at,
                     format: YYYY-MM-DD
    :param source: string 'alphavantage' or 'quandl', specifies the source
                   of the data

    ---> DataFrame, of end of day stock price data
    """

    # endpoints for each data source
    source_urls = {'alphavantage': 'https://www.alphavantage.co/query',
                   'quandl': 'https://www.quandl.com/api/v3/datasets/EOD/'}

    # API parameters for each data source
    source_params = {'alphavantage': {'function': 'TIME_SERIES_DAILY_ADJUSTED',
                                      'symbol': ticker, 'datatype': 'csv',
                                      'apikey': get_api_key(source),
                                      'outputsize': 'full'},
                     'quandl': {'api_key': get_api_key(source),
                                'download_type': 'full'}}

    # Setting endpoints
    url = source_urls[source]
    if source == 'quandl':
        url = url + ticker + '.csv'

    # Settings API parameters
    params = source_params[source]

    # Requesting API
    response = requests.get(url, params=params)

    # Creating DataFrame
    if source == 'alphavantage':
        date_col = 'timestamp'
    elif source == 'quandl':
        date_col = 'Date'
    df = pd.read_csv(io.StringIO(response.text), parse_dates=[date_col])

    # Slicing DataFrame
    if start_date != None:
        df = df.loc[df[date_col] >= start_date] # changed to = sign need to test
    if end_date != None:
        df = df.loc[df[date_col] <= end_date]

    # Renaming Columns
    df.columns = ['timestamp' if df[name].dtype == 'datetime64[ns]'
                  else '_'.join([name, ticker]) for name in df.columns]

    return df

def fetch_url_df(ticker, start_date, end_date, form_type='8-k'):
    """
    Returns a DataFrame  where each row consists of a forms filing date,
    and an url to the raw text version of the form.

    :param ticker: string, the SEC ticker number for the specific company or
                   stock ticker symbol
    :param start_date: string, date to start collecting data after,
                       format: YYYY-MM-DD
    :param end_date: string, date to end collecting data at,
                     format: YYYY-MM-DD
    :param form_type: string '8-k', '10-k', ..., the type of SEC form
                      to search for

    ---> DataFrame, of filing dates and urls to raw text versions of the
         specified form
    """

    edgar_url = 'https://www.sec.gov/cgi-bin/browse-edgar'

    edgar_params = {'action': 'getcompany', 'CIK': ticker, 'type': form_type,
                    'owner': 'exclude', 'count': '100', 'output': 'atom',
                    'start': ''}

    edgar_response = requests.get(edgar_url, params=edgar_params)

    soup = BeautifulSoup(edgar_response.text, 'lxml')

    all_docs = []
    # While the link to the next page existing is true
    while True:
        # Find all document entries on the page
        entries = soup.find_all('entry')
        # For each entry
        for entry in entries:
            # scrape the entry's filing date
            filing_date = entry.find('filing-date').text
            # Add entry url to list if its filing date meets certain requirements, CAN REFACTOR this section
            if (start_date == None) and (end_date == None):
                doc_link = re.sub('-index.htm.*', '.txt',
                                  entry.find('link')['href'])
                doc_entry = (filing_date, doc_link)
                all_docs.append(doc_entry)
            elif (start_date == None) and (end_date != None):
                if date.fromisoformat(filing_date) <= date.fromisoformat(end_date):
                    doc_link = re.sub('-index.htm.*', '.txt',
                                      entry.find('link')['href'])
                    doc_entry = (filing_date, doc_link)
                    all_docs.append(doc_entry)
            elif (start_date != None) and (end_date == None):
                if date.fromisoformat(filing_date) >= date.fromisoformat(start_date):
                    doc_link = re.sub('-index.htm.*', '.txt',
                                      entry.find('link')['href'])
                    doc_entry = (filing_date, doc_link)
                    all_docs.append(doc_entry)
            else:
                if date.fromisoformat(start_date) <= date.fromisoformat(filing_date) <= date.fromisoformat(end_date):
                    doc_link = re.sub('-index.htm.*', '.txt',
                                      entry.find('link')['href'])
                    doc_entry = (filing_date, doc_link)
                    all_docs.append(doc_entry)
        # Break loop after scraping entries on the current page, but before
        #  requesting on the link to the next page which is potentially none
        #  existant
        if soup.find_all('link', {'rel': 'next'}) == []:
            break
        # Find link to the next page, request next page, and update soup object
        #  to consist of the next page
        nxt_pg_link = soup.find_all('link', {'rel': 'next'})[0]['href']
        nxt_pg = requests.get(nxt_pg_link)
        soup = BeautifulSoup(nxt_pg.text, 'lxml')
    # Creating DataFrame
    doc_df = pd.DataFrame(all_docs,
                          columns=['filing_date',
                                   '{}_{}'.format(form_type, ticker)])
    doc_df['filing_date'] = pd.to_datetime(doc_df['filing_date'])

    # Reshaping DataFrame
    def json_list(el):
        return json.dumps(list(el))

    doc_df = (doc_df.groupby('filing_date')['{}_{}'.format(form_type, ticker)]
              .apply(json_list).reset_index().sort_values(by='filing_date',
                                                          ascending=False))

    return doc_df

# Functions for saving documents to disk

def save_doc(url, endpoint):
    """
    Downloads and saves the text file stored at :param url:, and saves it as
    its downloaded name in directory :param endpoint:.

    :param url: string, the url that points to the SEC text file
    :parame endpoint: string, path to location to save SEC filing

    ---> String, path to saved document
    """

    if not os.path.isdir(endpoint):
        os.makedirs(endpoint)
    try:
        r = requests.get(url)
    except Exception as e:
        raise Exception('error with url: {}'.format(url)) from e

    fname = url.split('/')[-1]
    with open(os.path.join(endpoint, fname), 'wb') as f:
        f.write(r.content)
    return os.path.join(endpoint, fname)

def save_docs(json_list, endpoint):
    """
    Downloads and saves each link in the :param json_list: at :param endpoint as
    a text file with the same name.

    :param json_list: string, json formated string of a list of urls
    :param endpoint: string, path to location to save SEC filings

    ---> String, json formated string of a list of paths to saved filings
    """

    urls = json.loads(json_list)
    paths = map(lambda url: save_doc(url, endpoint), urls)
    return json.dumps(list(paths))

# END Functions for saving documents to disk

def fetch_ticker_data(path_to_data, ticker, source, form_types, start_date, end_date):
    """
    Fetches all the data necessary for a specific ticker.

    :param ticker: string, stock ticker to fetch data for
    :param start_date: string, date to start collecting data at,
                       format: YYYY-MM-DD
    :param end_date: string, date to end collecting data at,
                     format: YYYY-MM-DD
    :form_types: list, of strings, of SEC form types to scrape for :param ticker:
    :source: string, either 'alphavantage' or 'quandl', specifying the source
             to use when obtaining the end of day stock ticker data

    ---> pandas.DataFrame, containing necessary data
    """

    price_df = fetch_stock_data(ticker, start_date, end_date, source)
    doc_dfs = map(lambda form_type: fetch_url_df(ticker, start_date, end_date, form_type), form_types)
    doc_df = reduce(lambda x, y: pd.merge(x, y, how='outer', on='filing_date'), doc_dfs, pd.DataFrame(columns=['filing_date']))
    df = pd.merge(price_df, doc_df, how='left', left_on='timestamp', right_on='filing_date')
    df = df.drop(columns=['filing_date'])
    # Filling NA values and downloading documents
    form_cols = ['{}_{}'.format(form_type, ticker) for form_type in form_types]
    # Filling NA values
    df[form_cols] = df[form_cols].fillna(value=json.dumps([]))
    # Scraping documents to path_to_data/documents/ticker
    for col in form_cols:
        df[col] = df[col].map(lambda json_list: save_docs(json_list, os.path.join(path_to_data, 'documents', ticker)))
    return df

def save_df(path_to_data, df, name='raw.csv'):
    """
    Writes pandas.DataFrame :param df: along with its meta data stored in
    pandas.DataFrame.attrs to the directory pointed to by :param path_to_data:.
    The meta data is stored as the JSON file meta.json.

    :param path_to_data: string, path to directory to save the pandas.DataFrame
                         to
    :param df: pandas.DataFrame, pandas.DataFrame to save
    :param name: string, name csv file to write pandas.DataFrame to

    ---> None
    """

    df.to_csv(os.path.join(path_to_data, name), index=False)
    with open(os.path.join(path_to_data, 'meta.json'), 'w') as f:
        meta_data = df.attrs
        try:
            del meta_data['path_to_data']
        except KeyError:
            pass
        json.dump(meta_data, f)

def load_df(path_to_data, name='raw.csv'):
    """
    Loads a pandas.DataFrame stored in the directory pointed to by
    :param path_to_data: along with its corresponding meta data stored in the
    same directory in file meta.json.

    :param path_to_data: string, path to directory where the pandas.DataFrame to
                         be loaded is stored
    :param name: string, name of the csv file to load the pandas.DataFrame from

    ---> pandas.DataFrame, where pandas.DataFrame.attrs is loaded with the meta
         data stored in the JSON file meta.json
    """

    df = pd.read_csv(os.path.join(path_to_data, name), parse_dates=['timestamp'])
    with open(os.path.join(path_to_data, 'meta.json'), 'r') as f:
        meta_data = json.load(f)
        meta_data['path_to_data'] = path_to_data
        df.attrs = meta_data
    return df

def fetch_data(path_to_data, tickers, source, form_types, start_date=None, end_date=None):
    """
    Docstring

    :param path_to_data: string,
    :param tickers: list of strings,
    :param source: string,
    :param form_types: string,
    :param start_date: string,
    :param end_date: string,

    ---> pandas.DataFrame, 
    """

    if not os.path.isdir(path_to_data):
        os.makedirs(path_to_data)
    data_dfs = map(lambda t: fetch_ticker_data(path_to_data, t, source, form_types, start_date, end_date), tickers)
    df = reduce(lambda x, y: pd.merge(x, y, how='outer', on='timestamp'), data_dfs)
    df.attrs = {'tickers': tickers, 'source': source, 'form_types': form_types}
    save_df(path_to_data, df)
    return df


#####################################
## END Functions for fetching data ##
#####################################
