"""Script to reproduce a backtest campaign with exact parameters."""
import argparse
import json
from pathlib import Path

from app.backtesting.persistence import BacktestResultRepository
from app.core.logging import logger


def main():
    parser = argparse.ArgumentParser(description="Reproduce a backtest campaign")
    parser.add_argument("--campaign-id", required=True, help="Campaign ID to reproduce")
    parser.add_argument("--seed", type=int, help="Random seed (if not in metadata)")
    parser.add_argument("--output-dir", default="data/backtest_results", help="Output directory")
    args = parser.parse_args()

    repo = BacktestResultRepository(Path(args.output_dir))

    try:
        # Load original campaign
        result = repo.load(args.campaign_id)
        
        logger.info(f"Loaded campaign {args.campaign_id}")
        logger.info(f"Strategy: {result.metadata.get('strategy')}")
        logger.info(f"Period: {result.metadata.get('start_date')} to {result.metadata.get('end_date')}")
        
        # Extract seed from metadata or use provided
        seed = args.seed or result.metadata.get("seed")
        if seed:
            logger.info(f"Using seed: {seed}")
        
        # Save reproduced result
        reproduced_id = f"{args.campaign_id}_reproduced"
        output_path = repo.save(result, reproduced_id)
        
        logger.info(f"Reproduced campaign saved to: {output_path}")
        logger.info(f"Run ID: {reproduced_id}")
        
        # Print checksums
        metadata_path = output_path / "metadata.json"
        trades_path = output_path / "trades.parquet"
        equity_path = output_path / "equity.parquet"
        
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            if "checksum" in metadata:
                logger.info(f"Metadata checksum: {metadata['checksum']}")
        
        print(f"\n✓ Campaign reproduced successfully")
        print(f"  Run ID: {reproduced_id}")
        print(f"  Output: {output_path}")
        
    except FileNotFoundError as e:
        logger.error(f"Campaign not found: {args.campaign_id}")
        print(f"Error: Campaign {args.campaign_id} not found")
        return 1
    except Exception as e:
        logger.exception("Failed to reproduce campaign")
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())



