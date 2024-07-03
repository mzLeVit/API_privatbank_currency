import aiohttp
import asyncio
import argparse
import logging
from datetime import datetime, timedelta
import websockets
from aiofile import AIOFile, Writer
from aiopath import AsyncPath

API_URL = "https://api.privatbank.ua/p24api/exchange_rates?json&date={}"

logging.basicConfig(level=logging.INFO)


class ExchangeRateFetcher:
    def __init__(self, days: int, currencies: list):
        self.days = days
        self.currencies = currencies

    async def fetch_exchange_rate(self, session, date):
        url = API_URL.format(date.strftime("%d.%m.%Y"))
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logging.error(f"Request failed: {e}")
            return None

    async def fetch_last_days(self, days=None):
        if days is None:
            days = self.days
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(days):
                date = datetime.now() - timedelta(days=i)
                tasks.append(self.fetch_exchange_rate(session, date))
            results = await asyncio.gather(*tasks)
            return results

    def extract_rates(self, data):
        rates = {}
        for entry in data:
            if entry:
                date = entry["date"]
                rates[date] = {rate["currency"]: rate["saleRate"] for rate in entry["exchangeRate"] if
                               rate["currency"] in self.currencies}
        return rates


async def main(days, currencies):
    fetcher = ExchangeRateFetcher(days, currencies)
    data = await fetcher.fetch_last_days()
    rates = fetcher.extract_rates(data)
    for date, rate in rates.items():
        print(f"Rates on {date}:")
        for currency, value in rate.items():
            print(f"{currency}: {value}")


class WebSocketChat:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.clients = set()

    async def exchange_command(self, websocket, params):
        days = int(params[0]) if params else 1
        if days > 10:
            await websocket.send("Error: Maximum number of days is 10")
            return

        data = await self.fetcher.fetch_last_days(days)
        rates = self.fetcher.extract_rates(data)

        response = []
        for date, rate in rates.items():
            response.append(f"Rates on {date}:")
            for currency, value in rate.items():
                response.append(f"{currency}: {value}")

        await websocket.send("\n".join(response))


        async with AIOFile('exchange.log', 'a') as afp:
            writer = Writer(afp)
            await writer(f"Command 'exchange' executed with params {params} at {datetime.now()}\n")

    async def handler(self, websocket, path):
        self.clients.add(websocket)
        try:
            async for message in websocket:
                command, *params = message.split()
                if command == "exchange":
                    await self.exchange_command(websocket, params)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"Connection closed: {e}")
        finally:
            self.clients.remove(websocket)

    async def start(self):
        server = await websockets.serve(self.handler, "localhost", 8765)
        await server.wait_closed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch exchange rates from PrivatBank API and run WebSocket chat")
    parser.add_argument("--days", type=int, default=1, help="Number of days to fetch rates for (max 10)")
    parser.add_argument("--currencies", type=str, nargs="+", default=["USD", "EUR"],
                        help="Currencies to fetch rates for")

    args = parser.parse_args()
    if args.days > 10:
        print("Error: Maximum number of days is 10")
    else:
        fetcher = ExchangeRateFetcher(args.days, args.currencies)


        asyncio.run(main(args.days, args.currencies))


        chat = WebSocketChat(fetcher)
        asyncio.run(chat.start())
