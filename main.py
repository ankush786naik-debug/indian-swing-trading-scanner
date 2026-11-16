
import argparse
import json

from Tej_client import TejClient, TejAPIError
from exporters import export_json, export_csv
from app.config import DEFAULT_EXCHANGE


def add_output_options(command):
    command.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json"
    )
    command.add_argument("--output", default=None)


def main():

    parser = argparse.ArgumentParser(
        description="TejHQ NSE Market Data Downloader"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True
    )

    p = commands.add_parser("ohlcv")
    p.add_argument("symbol")
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    p.add_argument("--from-date")
    p.add_argument("--to-date")
    p.add_argument("--adjusted", action="store_true")
    add_output_options(p)

    p = commands.add_parser("snapshot")
    p.add_argument("--date", required=True)
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    add_output_options(p)

    p = commands.add_parser("actions")
    p.add_argument("symbol")
    add_output_options(p)

    p = commands.add_parser("delivery")
    p.add_argument("symbol")
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    p.add_argument("--from-date")
    p.add_argument("--to-date")
    add_output_options(p)

    p = commands.add_parser("symbols")
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    p.add_argument("--symbol")
    p.add_argument("--isin")
    add_output_options(p)

    args = parser.parse_args()
    client = TejClient()

    try:

        if args.command == "ohlcv":

            method = (
                client.get_adjusted
                if args.adjusted
                else client.get_ohlcv
            )

            data = method(
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

            data = client.get_actions(args.symbol)

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

            if args.format == "csv":
                filename = (
                    filename if filename.endswith(".csv")
                    else filename + ".csv"
                )
                filepath = export_csv(data, filename)

            else:
                filename = (
                    filename if filename.endswith(".json")
                    else filename + ".json"
                )
                filepath = export_json(data, filename)

            print(f"Export successful: {filepath}")

        else:

            print(json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
                default=str
            ))

        if isinstance(data, list):
            print(f"Total records: {len(data)}")

    except (TejAPIError, ValueError) as error:
        print(f"API ERROR: {error}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
    
