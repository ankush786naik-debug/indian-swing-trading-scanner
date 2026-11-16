
import requests

from config import (
    API_BASE_URL,
    API_KEY,
    REQUEST_TIMEOUT
)


class TejAPIError(Exception):
    """Custom TejHQ API exception."""
    pass


class TejClient:

    def __init__(self):
        self.session = requests.Session()

        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "NSE-Market-Data-Client/1.0"
        })

        if API_KEY:
            self.session.headers.update({
                "Authorization": f"Bearer {API_KEY}"
            })

    def request(self, endpoint, params=None):

        url = f"{API_BASE_URL}{endpoint}"

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 401:
                raise TejAPIError(
                    "Authentication required. Check your TejHQ API key."
                )

            if response.status_code == 402:
                raise TejAPIError(
                    "This endpoint requires a paid TejHQ subscription."
                )

            if response.status_code == 429:
                raise TejAPIError(
                    "Rate limit exceeded. Please retry later."
                )

            response.raise_for_status()

            result = response.json()

            if isinstance(result, dict) and result.get("error"):
                raise TejAPIError(str(result["error"]))

            return result

        except requests.exceptions.Timeout:
            raise TejAPIError("TejHQ API request timed out.")

        except requests.exceptions.RequestException as error:
            raise TejAPIError(
                f"TejHQ connection error: {error}"
            )

        except ValueError:
            raise TejAPIError(
                "TejHQ returned invalid JSON."
            )

    @staticmethod
    def extract_data(response):

        if isinstance(response, dict):
            return response.get("data", response)

        return response

    def get_ohlcv(
        self,
        symbol,
        exchange="nse",
        from_date=None,
        to_date=None
    ):

        params = {}
        symbol = symbol.upper().strip()

for suffix in (".NSE", ".NS"):
    if symbol.endswith(suffix):
        symbol = symbol[:-len(suffix)]
        break

        if from_date:
            params["from"] = from_date

        if to_date:
            params["to"] = to_date

        result = self.request(
            f"/v1/ohlcv/{exchange}/{symbol.upper()}",
            params
        )

        return self.extract_data(result)

    def get_snapshot(
        self,
        exchange="nse",
        date=None
    ):

        if not date:
            raise ValueError("Snapshot date is required.")

        result = self.request(
            f"/v1/snapshot/{exchange}",
            {"date": date}
        )

        return self.extract_data(result)

    def get_actions(self, symbol):

        result = self.request(
            f"/v1/actions/{symbol.upper()}"
        )

        return self.extract_data(result)

    def get_adjusted(
        self,
        symbol,
        exchange="nse",
        from_date=None,
        to_date=None
    ):

        params = {}

        if from_date:
            params["from"] = from_date

        if to_date:
            params["to"] = to_date

        result = self.request(
            f"/v1/adjusted/{exchange}/{symbol.upper()}",
            params
        )

        return self.extract_data(result)

    def get_delivery(
        self,
        symbol,
        exchange="nse",
        from_date=None,
        to_date=None
    ):

        params = {}

        if from_date:
            params["from"] = from_date

        if to_date:
            params["to"] = to_date

        result = self.request(
            f"/v1/delivery/{exchange}/{symbol.upper()}",
            params
        )

        return self.extract_data(result)

    def get_symbols(
        self,
        exchange="nse",
        symbol=None,
        isin=None
    ):

        params = {}

        if symbol:
            params["symbol"] = symbol

        if isin:
            params["isin"] = isin

        result = self.request(
            f"/v1/symbols/{exchange}",
            params
        )

        return self.extract_data(result)

    def close(self):
        self.session.close()
  
