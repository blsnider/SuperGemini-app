"""
Seasonality configuration for overstock analysis
Maps season codes to their active date ranges and scoring weights
"""

from datetime import datetime, date
from typing import Dict, Tuple, Optional

SEASON_DEFINITIONS = {
    'Y': {
        'name': 'Year-Round',
        'months': list(range(1, 13)),  # January through December
        'date_ranges': [(1, 1, 12, 31)],  # (start_month, start_day, end_month, end_day)
        'weight': 0.5  # Lower weight as these items sell year-round
    },
    'S': {
        'name': 'Spring',
        'months': [1, 2, 3],  # January through March
        'date_ranges': [(1, 1, 3, 31)],
        'weight': 1.0  # Full weight during season
    },
    'E': {
        'name': 'Early Year',
        'months': list(range(1, 7)),  # January through June
        'date_ranges': [(1, 1, 6, 30)],
        'weight': 0.8
    },
    'U': {
        'name': 'Summer',
        'months': [4, 5, 6],  # April through June
        'date_ranges': [(4, 1, 6, 30)],
        'weight': 1.0
    },
    'L': {
        'name': 'Late Year',
        'months': list(range(7, 13)),  # July through December
        'date_ranges': [(7, 1, 12, 31)],
        'weight': 0.8
    },
    'F': {
        'name': 'Fall',
        'months': [7, 8, 9],  # July through September
        'date_ranges': [(7, 1, 9, 30)],
        'weight': 1.0
    },
    'H': {
        'name': 'Holiday',
        'months': [10, 11, 12],  # October through December
        'date_ranges': [(10, 1, 12, 31)],
        'weight': 1.2  # Higher weight for holiday season
    },
    'W': {
        'name': 'Winter',
        'months': [10, 11, 12, 1, 2],  # October through February
        'date_ranges': [(10, 1, 12, 31), (1, 1, 2, 15)],  # Spans year boundary
        'weight': 1.0
    }
}

def is_in_season(season_code: str, check_date: Optional[date] = None) -> bool:
    """
    Check if a given date falls within the season for a specific season code
    
    Args:
        season_code: Single character season code (Y, S, E, U, L, F, H, W)
        check_date: Date to check (defaults to today)
    
    Returns:
        True if the date is within the season, False otherwise
    """
    if check_date is None:
        check_date = date.today()
    
    if season_code not in SEASON_DEFINITIONS:
        return False
    
    season = SEASON_DEFINITIONS[season_code]
    current_month = check_date.month
    current_day = check_date.day
    
    for start_month, start_day, end_month, end_day in season['date_ranges']:
        # Handle ranges that don't cross year boundary
        if start_month <= end_month:
            if (current_month > start_month or 
                (current_month == start_month and current_day >= start_day)) and \
               (current_month < end_month or 
                (current_month == end_month and current_day <= end_day)):
                return True
        # Handle ranges that cross year boundary (like Winter)
        else:
            if (current_month > start_month or 
                (current_month == start_month and current_day >= start_day)) or \
               (current_month < end_month or 
                (current_month == end_month and current_day <= end_day)):
                return True
    
    return False

def is_approaching_season(season_code: str, days_ahead: int = 30, check_date: Optional[date] = None) -> bool:
    """
    Check if we're approaching a season within specified days
    
    Args:
        season_code: Single character season code
        days_ahead: Number of days to look ahead (default 30)
        check_date: Date to check from (defaults to today)
    
    Returns:
        True if season starts within the specified days ahead
    """
    if check_date is None:
        check_date = date.today()
    
    if season_code not in SEASON_DEFINITIONS:
        return False
    
    season = SEASON_DEFINITIONS[season_code]
    
    # Check each date in the look-ahead period
    from datetime import timedelta
    for i in range(days_ahead + 1):
        future_date = check_date + timedelta(days=i)
        if is_in_season(season_code, future_date) and not is_in_season(season_code, check_date):
            return True
    
    return False

def get_seasonality_weight(season_code: str, check_date: Optional[date] = None) -> float:
    """
    Get the seasonality weight for overstock scoring
    
    Args:
        season_code: Single character season code
        check_date: Date to check (defaults to today)
    
    Returns:
        Weight factor (0.0 to 1.5) for overstock scoring
        - 0.0: Out of season (consider for overstock)
        - 0.5-0.8: Partial season or year-round
        - 1.0: In season
        - 1.2+: Peak season (holiday)
    """
    if check_date is None:
        check_date = date.today()
    
    if season_code not in SEASON_DEFINITIONS:
        return 0.5  # Default neutral weight for unknown seasons
    
    if is_in_season(season_code, check_date):
        return SEASON_DEFINITIONS[season_code]['weight']
    elif is_approaching_season(season_code, days_ahead=60, check_date=check_date):
        # Approaching season gets partial weight
        return SEASON_DEFINITIONS[season_code]['weight'] * 0.7
    else:
        # Out of season
        return 0.0

def generate_season_sql_case() -> str:
    """
    Generate SQL CASE statement for season detection
    Returns a SQL snippet that can be used in BigQuery
    """
    sql_parts = ["CASE"]
    
    for code, definition in SEASON_DEFINITIONS.items():
        conditions = []
        for start_month, start_day, end_month, end_day in definition['date_ranges']:
            if start_month <= end_month:
                # Season doesn't cross year boundary
                condition = f"""(EXTRACT(MONTH FROM CURRENT_DATE()) > {start_month} OR 
                               (EXTRACT(MONTH FROM CURRENT_DATE()) = {start_month} AND EXTRACT(DAY FROM CURRENT_DATE()) >= {start_day}))
                              AND 
                              (EXTRACT(MONTH FROM CURRENT_DATE()) < {end_month} OR 
                               (EXTRACT(MONTH FROM CURRENT_DATE()) = {end_month} AND EXTRACT(DAY FROM CURRENT_DATE()) <= {end_day}))"""
            else:
                # Season crosses year boundary (like Winter)
                condition = f"""((EXTRACT(MONTH FROM CURRENT_DATE()) > {start_month} OR 
                                (EXTRACT(MONTH FROM CURRENT_DATE()) = {start_month} AND EXTRACT(DAY FROM CURRENT_DATE()) >= {start_day}))
                               OR 
                               (EXTRACT(MONTH FROM CURRENT_DATE()) < {end_month} OR 
                                (EXTRACT(MONTH FROM CURRENT_DATE()) = {end_month} AND EXTRACT(DAY FROM CURRENT_DATE()) <= {end_day})))"""
            conditions.append(f"({condition})")
        
        if conditions:
            combined_condition = " OR ".join(conditions)
            sql_parts.append(f"  WHEN season_code = '{code}' AND ({combined_condition}) THEN {definition['weight']}")
    
    sql_parts.append("  ELSE 0.5")  # Default weight
    sql_parts.append("END")
    
    return "\n".join(sql_parts)