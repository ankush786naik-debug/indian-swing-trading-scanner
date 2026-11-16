
import argparse
import json

from app.tej_client import TejClient, TejAPIError
from app.exporters import export_json, export_csv
from app.config import DEFAULT_EXCHANGE


def main():

    parser = argparse.ArgumentParser(
        description="TejHQ NSE Market Data Downloader"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )

    # Historical prices
    ohlcv = subparsers.add_parser("ohlcv")
    ohlcv.add_argument("symbol")
    ohlcv.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    ohlcv.add_argument("--from-date")
    ohlcv.add_argument("--to-date")
    ohlcv.add_argument("--adjusted", action="store_true")

    # Market snapshot
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--date", required=True)
    snapshot.add_argument("--exchange", default=DEFAULT_EXCHANGE)

    # Corporate actions
    actions = subparsers.add_parser("actions")
    actions.add_argument("symbol")

    # Delivery data
    delivery = subparsers.add_parser("delivery")
    delivery.add_argument("symbol")
    delivery.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    delivery.add_argument("--from-date")
    delivery.add_argument("--to-date")

    # Symbol history
    symbols = subparsers.add_parser("symbols")
    symbols.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    symbols.add_argument("--symbol")
    symbols.add_argument("--isin")

    # Output format
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json"
    )

    parser.add_argument(
        "--output",
        default=None
    )

    args = parser.parse_args()

    client = TejClient()

    try:

        if args.command == "ohlcv":

            if args.adjusted:
                data = client.get_adjusted(
                    args.symbol,
                    args.exchange,
                    args.from_date,
                    args.to_date
                )
            else:
                data = client.get_ohlcv(
                    args.symbol,
                    args.exchange,
                    args.from_date,
                    args.to_date
                )

        elif args.command == "snapshot":

            data = client.get_snapshot(
                args.exchange,
                args.date
            )

        elif args.command == "actions":

            data = client.get_actions(
                args.symbol
            )

        elif args.command == "delivery":

            data = client.get_delivery(
                args.symbol,
                args.exchange,
                args.from_date,
                args.to_date
            )

        elif args.command == "symbols":

            data = client.get_symbols(
                args.exchange,
                args.symbol,
                args.isin
            )

        if args.output:

            filename = args.output

            if args.format == "json":
                if not filename.endswith(".json"):
                    filename += ".json"

                filepath = export_json(
                    data,
                    filename
                )

            else:
                if not filename.endswith(".csv"):
                    filename += ".csv"

                filepath = export_csv(
                    data,
                    filename
                )

            print(f"Saved: {filepath}")

        else:

            print(json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
                default=str
            ))

        if isinstance(data, list):
            print(f"\nTotal records: {len(data)}")

    except (TejAPIError, ValueError) as error:

        print(f"ERROR: {error}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
          
