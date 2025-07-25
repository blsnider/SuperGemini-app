"""
Weighting Logic for Inventory Coverage Analysis and Priority Scoring with Returns Analysis
"""

import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    ADEQUATE = "Adequate"
    OVERSTOCKED = "Overstocked"


class ActionGroup(Enum):
    URGENT_REORDERS = "Urgent Reorders"
    REVIEW_REQUIRED = "Review Required"
    MONITORING = "Monitoring"
    ADEQUATE = "Adequate"


@dataclass
class CoverageMetrics:
    """Data class to hold coverage analysis metrics including returns data"""
    on_hand_units: float
    units_on_order: float
    forecasted_units: Optional[float]
    current_period_sales: Optional[float]
    last_year_sales: Optional[float]
    sales_value: float
    margin_percentage: float
    sell_through_percentage: float
    mog: int  # Minimum Order Quantity
    box_per_case: int
    is_active: bool = True
    # Additional metrics for enhanced review flags
    demand_variability: float = 0  # Coefficient of variation
    sales_trend: str = 'Stable'  # Increasing/Decreasing/Stable
    yoy_growth_pct: float = 0
    is_new_item: bool = False
    is_seasonal: bool = False
    days_with_sales: int = 0
    inventory_value: float = 0
    units_sold_last_7d: float = 0
    units_sold_prev_7d: float = 0
    # Returns metrics
    return_count_30d: int = 0
    return_days_30d: int = 0
    return_rate_pct: float = 0


class WeightingCalculator:
    """Calculates coverage analysis, risk levels, and priority scores including returns analysis"""
    
    # Weight factors for priority scoring
    COVERAGE_WEIGHT = 0.35  # Reduced slightly to accommodate returns
    SALES_VALUE_WEIGHT = 0.25
    SELL_THROUGH_WEIGHT = 0.20
    MARGIN_WEIGHT = 0.10
    RETURN_RISK_WEIGHT = 0.10  # New weight for return risk
    
    # Risk level thresholds
    CRITICAL_THRESHOLD = 25
    HIGH_THRESHOLD = 50
    MEDIUM_THRESHOLD = 75
    LOW_THRESHOLD = 100
    ADEQUATE_THRESHOLD = 150
    
    # Return risk thresholds
    HIGH_RETURN_RATE_THRESHOLD = 15  # >15% return rate is high risk
    MODERATE_RETURN_RATE_THRESHOLD = 8  # >8% return rate is moderate risk
    HIGH_RETURN_COUNT_THRESHOLD = 5  # >5 returns in 30 days is high risk
    
    # Other thresholds
    OVERBUY_BUFFER = 1.2
    LOW_SELL_THROUGH_THRESHOLD = 10
    INACTIVE_COVERAGE_THRESHOLD = 50
    
    def calculate_coverage_analysis(self, metrics: CoverageMetrics) -> Dict:
        """
        Performs complete coverage analysis for an item including returns risk assessment
        
        Returns:
            Dict containing all coverage metrics, risk levels, returns analysis, and recommendations
        """
        # 1. Calculate current coverage
        current_coverage = metrics.on_hand_units + metrics.units_on_order
        
        # 2. Determine expected demand (priority order)
        expected_demand = self._calculate_expected_demand(metrics)
        
        # 3. Calculate coverage gap
        coverage_gap = max(0, expected_demand - current_coverage)
        
        # 4. Calculate coverage percentage
        coverage_percentage = self._safe_divide(current_coverage, expected_demand) * 100
        
        # 5. Determine risk level (now includes returns risk)
        risk_level = self._determine_risk_level(coverage_percentage, metrics)
        
        # 6. Calculate priority score (now includes returns risk)
        priority_score = self._calculate_priority_score(
            coverage_percentage, 
            metrics.sales_value,
            metrics.sell_through_percentage,
            metrics.margin_percentage,
            metrics.return_rate_pct
        )
        
        # 7. Calculate recommended order quantity
        recommended_qty = self._calculate_recommended_order_qty(
            coverage_gap, 
            metrics.mog, 
            metrics.box_per_case
        )
        
        # 8. Calculate overbuy threshold
        overbuy_threshold = self._calculate_overbuy_threshold(
            metrics.forecasted_units,
            metrics.current_period_sales,
            metrics.last_year_sales,
            current_coverage
        )
        
        # 9. Determine review flags (now includes returns flags)
        review_flags = self._determine_review_flags(
            coverage_percentage,
            metrics.current_period_sales,
            metrics.last_year_sales,
            metrics.sell_through_percentage,
            metrics.is_active,
            recommended_qty,
            overbuy_threshold,
            metrics  # Pass the entire metrics object
        )
        
        # 10. Determine action group (now considers returns)
        action_group = self._determine_action_group(risk_level, review_flags, metrics)
        
        # 11. Calculate returns risk assessment
        returns_risk = self._calculate_returns_risk(metrics)
        
        return {
            'current_coverage': current_coverage,
            'expected_demand': expected_demand,
            'coverage_gap': coverage_gap,
            'coverage_percentage': coverage_percentage,
            'risk_level': risk_level.value,
            'priority_score': priority_score,
            'recommended_order_qty': recommended_qty,
            'overbuy_threshold': overbuy_threshold,
            'exceeds_overbuy': recommended_qty > overbuy_threshold if overbuy_threshold else False,
            'review_flags': review_flags,
            'action_group': action_group.value,
            'returns_analysis': returns_risk,
            'calculations': {
                'coverage_score': self._calculate_coverage_score(coverage_percentage),
                'sales_value_score': self._normalize_score(metrics.sales_value, 0, 10000),
                'sell_through_score': metrics.sell_through_percentage,
                'margin_score': metrics.margin_percentage,
                'return_risk_score': self._calculate_return_risk_score(metrics.return_rate_pct)
            }
        }
    
    def _calculate_expected_demand(self, metrics: CoverageMetrics) -> float:
        """Calculate expected demand using priority order"""
        if metrics.forecasted_units and metrics.forecasted_units > 0:
            return metrics.forecasted_units
        elif metrics.current_period_sales and metrics.current_period_sales > 0:
            return metrics.current_period_sales
        elif metrics.last_year_sales and metrics.last_year_sales > 0:
            return metrics.last_year_sales
        else:
            return 0
    
    def _determine_risk_level(self, coverage_percentage: float, metrics: CoverageMetrics) -> RiskLevel:
        """Determine risk level based on coverage percentage and returns data"""
        base_risk = self._get_base_risk_level(coverage_percentage)
        
        # Escalate risk if high returns
        if metrics.return_rate_pct > self.HIGH_RETURN_RATE_THRESHOLD:
            if base_risk == RiskLevel.LOW:
                return RiskLevel.MEDIUM
            elif base_risk == RiskLevel.MEDIUM:
                return RiskLevel.HIGH
            elif base_risk == RiskLevel.ADEQUATE:
                return RiskLevel.MEDIUM
        elif metrics.return_rate_pct > self.MODERATE_RETURN_RATE_THRESHOLD:
            if base_risk == RiskLevel.ADEQUATE:
                return RiskLevel.LOW
        
        return base_risk
    
    def _get_base_risk_level(self, coverage_percentage: float) -> RiskLevel:
        """Get base risk level based on coverage percentage only"""
        if coverage_percentage < self.CRITICAL_THRESHOLD:
            return RiskLevel.CRITICAL
        elif coverage_percentage < self.HIGH_THRESHOLD:
            return RiskLevel.HIGH
        elif coverage_percentage < self.MEDIUM_THRESHOLD:
            return RiskLevel.MEDIUM
        elif coverage_percentage < self.LOW_THRESHOLD:
            return RiskLevel.LOW
        elif coverage_percentage <= self.ADEQUATE_THRESHOLD:
            return RiskLevel.ADEQUATE
        else:
            return RiskLevel.OVERSTOCKED
    
    def _calculate_priority_score(self, coverage_pct: float, sales_value: float, 
                                 sell_through_pct: float, margin_pct: float,
                                 return_rate_pct: float) -> float:
        """
        Calculate priority score (0-100) based on weighted factors including returns risk
        Higher score = higher priority
        """
        # Coverage score: Lower coverage = higher score
        coverage_score = self._calculate_coverage_score(coverage_pct)
        
        # Sales value score: Normalize to 0-100
        sales_value_score = self._normalize_score(sales_value, 0, 10000)
        
        # Sell-through score: Direct percentage
        sell_through_score = sell_through_pct
        
        # Margin score: Direct percentage
        margin_score = margin_pct
        
        # Return risk score: Higher return rate = higher priority (need attention)
        return_risk_score = self._calculate_return_risk_score(return_rate_pct)
        
        # Calculate weighted score
        priority_score = (
            coverage_score * self.COVERAGE_WEIGHT +
            sales_value_score * self.SALES_VALUE_WEIGHT +
            sell_through_score * self.SELL_THROUGH_WEIGHT +
            margin_score * self.MARGIN_WEIGHT +
            return_risk_score * self.RETURN_RISK_WEIGHT
        )
        
        return round(min(100, max(0, priority_score)), 2)
    
    def _calculate_coverage_score(self, coverage_pct: float) -> float:
        """Convert coverage percentage to score (lower coverage = higher score)"""
        if coverage_pct >= 100:
            return 0
        else:
            return 100 - coverage_pct
    
    def _calculate_return_risk_score(self, return_rate_pct: float) -> float:
        """Convert return rate to risk score (higher return rate = higher score)"""
        if return_rate_pct >= self.HIGH_RETURN_RATE_THRESHOLD:
            return 100
        elif return_rate_pct >= self.MODERATE_RETURN_RATE_THRESHOLD:
            return 60
        elif return_rate_pct > 0:
            return min(50, return_rate_pct * 6)  # Scale up to 50 for rates up to ~8%
        else:
            return 0
    
    def _normalize_score(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize a value to 0-100 scale"""
        if max_val <= min_val:
            return 0
        normalized = ((value - min_val) / (max_val - min_val)) * 100
        return min(100, max(0, normalized))
    
    def _calculate_recommended_order_qty(self, gap: float, moq: int, box_per_case: int) -> int:
        """
        Calculate recommended order quantity based on gap and constraints
        Rounds up to meet MOQ and case pack requirements
        """
        if gap <= 0:
            return 0
        
        # Determine the constraint to use
        constraint = max(moq, box_per_case)
        
        if constraint <= 1:
            return int(gap)
        
        # Round up to nearest constraint multiple
        return int(((gap - 1) // constraint + 1) * constraint)
    
    def _calculate_overbuy_threshold(self, forecast: Optional[float], 
                                   current_sales: Optional[float],
                                   last_year_sales: Optional[float],
                                   current_coverage: float) -> Optional[float]:
        """Calculate overbuy threshold with 20% safety buffer"""
        if last_year_sales and last_year_sales > 0:
            base_demand = forecast if forecast and forecast > 0 else last_year_sales
            return (base_demand - current_coverage) * self.OVERBUY_BUFFER
        elif current_sales and current_sales > 0:
            return (current_sales - current_coverage) * self.OVERBUY_BUFFER
        else:
            return None
    
    def _calculate_returns_risk(self, metrics: CoverageMetrics) -> Dict:
        """Calculate comprehensive returns risk assessment"""
        risk_level = "Low"
        risk_factors = []
        recommendations = []
        
        # Determine risk level
        if metrics.return_rate_pct > self.HIGH_RETURN_RATE_THRESHOLD:
            risk_level = "High"
            risk_factors.append(f"High return rate ({metrics.return_rate_pct:.1f}%)")
        elif metrics.return_rate_pct > self.MODERATE_RETURN_RATE_THRESHOLD:
            risk_level = "Moderate"
            risk_factors.append(f"Moderate return rate ({metrics.return_rate_pct:.1f}%)")
        
        if metrics.return_count_30d > self.HIGH_RETURN_COUNT_THRESHOLD:
            risk_factors.append(f"High return frequency ({metrics.return_count_30d} returns in 30 days)")
            if risk_level == "Low":
                risk_level = "Moderate"
        
        # Return pattern analysis
        if metrics.return_days_30d > 0:
            avg_returns_per_day = metrics.return_count_30d / metrics.return_days_30d
            if avg_returns_per_day > 1.5:
                risk_factors.append("Clustered return pattern - multiple returns per day")
        
        # Generate recommendations based on risk factors
        if risk_level == "High":
            recommendations.extend([
                "Investigate product quality issues",
                "Review supplier/vendor performance",
                "Consider temporary stock reduction",
                "Analyze return reasons and customer feedback"
            ])
        elif risk_level == "Moderate":
            recommendations.extend([
                "Monitor return trends closely",
                "Review product descriptions and specifications",
                "Consider customer education/training materials"
            ])
        
        return {
            'risk_level': risk_level,
            'return_rate_pct': metrics.return_rate_pct,
            'return_count_30d': metrics.return_count_30d,
            'return_days_30d': metrics.return_days_30d,
            'risk_factors': risk_factors,
            'recommendations': recommendations
        }
    
    def _determine_review_flags(self, coverage_pct: float, current_sales: Optional[float],
                              last_year_sales: Optional[float], sell_through_pct: float,
                              is_active: bool, recommended_qty: int, 
                              overbuy_threshold: Optional[float], metrics: CoverageMetrics) -> list:
        """Determine which review flags apply to this item, including returns flags"""
        flags = []
        
        # Original flags
        if coverage_pct > self.ADEQUATE_THRESHOLD:
            flags.append("Overstocked")
        
        if (not current_sales or current_sales == 0) and (not last_year_sales or last_year_sales == 0):
            flags.append("No sales history")
        
        if sell_through_pct < self.LOW_SELL_THROUGH_THRESHOLD:
            flags.append("Low sell-through")
        
        if not is_active and coverage_pct > self.INACTIVE_COVERAGE_THRESHOLD:
            flags.append("Inactive with coverage")
        
        if overbuy_threshold and recommended_qty > overbuy_threshold:
            flags.append("Exceeds overbuy threshold")
        
        # Enhanced review flags
        if metrics.demand_variability > 1.5:
            flags.append("High demand variability")
        
        if metrics.sales_trend == 'Decreasing' and metrics.on_hand_units > (metrics.units_sold_last_7d * 8):
            flags.append("Declining sales with high stock")
        
        if metrics.is_new_item and metrics.days_with_sales < 30:
            flags.append("New item - limited history")
        
        if metrics.yoy_growth_pct < -50 and metrics.on_hand_units > 0:
            flags.append("Significant YoY decline")
        
        if metrics.inventory_value > 1000 and (not current_sales or current_sales == 0):
            flags.append("Dead stock risk - high value")
        
        if 0 < metrics.margin_percentage < 20:
            flags.append("Low margin item")
        
        if metrics.is_seasonal and metrics.on_hand_units > (self._calculate_expected_demand(metrics) * 0.5):
            flags.append("Seasonal item with high stock")
        
        if metrics.mog > (metrics.units_sold_last_7d * 12):
            flags.append("MOQ exceeds 12 weeks supply")
        
        if 0 < metrics.days_with_sales < 10:
            flags.append("Sporadic sales pattern")
        
        # Returns-specific flags
        if metrics.return_rate_pct > self.HIGH_RETURN_RATE_THRESHOLD:
            flags.append(f"High return rate ({metrics.return_rate_pct:.1f}%)")
        elif metrics.return_rate_pct > self.MODERATE_RETURN_RATE_THRESHOLD:
            flags.append(f"Moderate return rate ({metrics.return_rate_pct:.1f}%)")
        
        if metrics.return_count_30d > self.HIGH_RETURN_COUNT_THRESHOLD:
            flags.append(f"High return frequency ({metrics.return_count_30d} returns)")
        
        if metrics.return_rate_pct > self.MODERATE_RETURN_RATE_THRESHOLD and coverage_pct > 100:
            flags.append("High returns with excess inventory")
        
        return flags
    
    def _determine_action_group(self, risk_level: RiskLevel, review_flags: list, metrics: CoverageMetrics = None) -> ActionGroup:
        """Categorize item into actionable group, considering returns risk"""
        # Priority for review based on specific conditions
        critical_review_flags = [
            "Dead stock risk - high value",
            "Significant YoY decline",
            "Declining sales with high stock",
            "High demand variability",
            "High return rate",
            "High returns with excess inventory"
        ]
        
        returns_review_flags = [
            "High return rate",
            "Moderate return rate",
            "High return frequency",
            "High returns with excess inventory"
        ]
        
        # Check for returns-specific review needs
        has_return_issues = any(flag for flag in review_flags if any(return_flag in flag for return_flag in returns_review_flags))
        
        if any(flag in review_flags for flag in critical_review_flags):
            return ActionGroup.REVIEW_REQUIRED
        elif has_return_issues:
            return ActionGroup.REVIEW_REQUIRED
        elif review_flags:
            return ActionGroup.REVIEW_REQUIRED
        elif risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
            # Don't mark new items as urgent if they have limited history
            if metrics and metrics.is_new_item and metrics.days_with_sales < 30:
                return ActionGroup.MONITORING
            return ActionGroup.URGENT_REORDERS
        elif risk_level == RiskLevel.MEDIUM:
            return ActionGroup.MONITORING
        else:
            return ActionGroup.ADEQUATE
    
    def _safe_divide(self, numerator: float, denominator: float) -> float:
        """Safely divide two numbers, returning 0 if denominator is 0"""
        return numerator / denominator if denominator != 0 else 0


def get_weighting_sql_enhancement() -> str:
    """
    Returns SQL code to enhance the base query with weighting calculations including returns
    This can be added as additional CTEs or columns to the main query
    """
    return """
    -- Extract MOQ/Box Case from sku_description2
    sku_with_moq AS (
        SELECT 
            *,
            CASE 
                WHEN REGEXP_CONTAINS(sku_description2, r'MO#\s*(\d+)') 
                THEN CAST(REGEXP_EXTRACT(sku_description2, r'MO#\s*(\d+)') AS INT64)
                ELSE 1
            END as moq_box_case
        FROM base_skus
    ),
    -- Enhanced weighting calculations with returns analysis
    weighting_calcs AS (
        SELECT 
            *,
            -- Coverage calculations
            current_on_hand + COALESCE(units_on_order, 0) as current_coverage,
            CASE 
                WHEN COALESCE(forecast_units, 0) > 0 THEN forecast_units
                WHEN COALESCE(units_sold_current_period, 0) > 0 THEN units_sold_current_period
                ELSE COALESCE(units_sold_last_year, 0)
            END as expected_demand,
            
            -- Coverage percentage
            SAFE_DIVIDE(
                current_on_hand + COALESCE(units_on_order, 0),
                CASE 
                    WHEN COALESCE(forecast_units, 0) > 0 THEN forecast_units
                    WHEN COALESCE(units_sold_current_period, 0) > 0 THEN units_sold_current_period
                    ELSE COALESCE(units_sold_last_year, 0)
                END
            ) * 100 as coverage_percentage,
            
            -- Sell-through percentage
            SAFE_DIVIDE(
                units_sold_current_period,
                units_sold_current_period + current_on_hand
            ) * 100 as sell_through_percentage,
            
            -- Return rate percentage
            SAFE_DIVIDE(
                COALESCE(return_count_30d, 0),
                NULLIF(units_sold_30d, 0)
            ) * 100 as return_rate_pct,
            
            -- Sales trend
            CASE 
                WHEN units_sold_last_7d > units_sold_prev_7d * 1.2 THEN 'Increasing'
                WHEN units_sold_last_7d < units_sold_prev_7d * 0.8 THEN 'Decreasing'
                ELSE 'Stable'
            END as sales_trend,
            
            -- Demand variability (CV)
            STDDEV(daily_sales) / NULLIF(AVG(daily_sales), 0) as demand_variability,
            
            -- Risk level (enhanced with returns consideration)
            CASE 
                WHEN SAFE_DIVIDE(current_on_hand + COALESCE(units_on_order, 0), expected_demand) * 100 < 25 
                     OR SAFE_DIVIDE(COALESCE(return_count_30d, 0), NULLIF(units_sold_30d, 0)) * 100 > 15 
                     THEN 'Critical'
                WHEN SAFE_DIVIDE(current_on_hand + COALESCE(units_on_order, 0), expected_demand) * 100 < 50 
                     OR SAFE_DIVIDE(COALESCE(return_count_30d, 0), NULLIF(units_sold_30d, 0)) * 100 > 8 
                     THEN 'High'
                WHEN SAFE_DIVIDE(current_on_hand + COALESCE(units_on_order, 0), expected_demand) * 100 < 75 THEN 'Medium'
                WHEN SAFE_DIVIDE(current_on_hand + COALESCE(units_on_order, 0), expected_demand) * 100 < 100 THEN 'Low'
                WHEN SAFE_DIVIDE(current_on_hand + COALESCE(units_on_order, 0), expected_demand) * 100 <= 150 THEN 'Adequate'
                ELSE 'Overstocked'
            END as risk_level,
            
            -- Priority score components (0-100 scale) with returns weight
            CASE 
                WHEN SAFE_DIVIDE(current_on_hand + COALESCE(units_on_order, 0), expected_demand) * 100 >= 100 THEN 0
                ELSE 100 - SAFE_DIVIDE(current_on_hand + COALESCE(units_on_order, 0), expected_demand) * 100
            END as coverage_score,
            
            -- Sales value score: normalized to 0-100
            SAFE_DIVIDE(total_revenue, 10000) * 100 as sales_value_score,
            
            -- Margin score: direct percentage
            margin_percentage as margin_score,
            
            -- Return risk score: higher return rate = higher priority
            CASE 
                WHEN SAFE_DIVIDE(COALESCE(return_count_30d, 0), NULLIF(units_sold_30d, 0)) * 100 >= 15 THEN 100
                WHEN SAFE_DIVIDE(COALESCE(return_count_30d, 0), NULLIF(units_sold_30d, 0)) * 100 >= 8 THEN 60
                WHEN SAFE_DIVIDE(COALESCE(return_count_30d, 0), NULLIF(units_sold_30d, 0)) * 100 > 0 
                     THEN SAFE_DIVIDE(COALESCE(return_count_30d, 0), NULLIF(units_sold_30d, 0)) * 100 * 6
                ELSE 0
            END as return_risk_score,
            
            -- Inventory value for dead stock risk
            current_on_hand * avg_unit_cost as inventory_value
            
        FROM sku_with_moq
    ),
    final_scoring AS (
        SELECT 
            *,
            -- Calculate weighted priority score with returns consideration
            (coverage_score * 0.35 + 
             sales_value_score * 0.25 + 
             sell_through_percentage * 0.20 + 
             margin_score * 0.10 +
             return_risk_score * 0.10) as priority_score,
             
            -- Recommended order quantity with MOQ/case pack constraints
            CASE 
                WHEN expected_demand - current_coverage <= 0 THEN 0
                ELSE CEIL((expected_demand - current_coverage) / GREATEST(moq_box_case, 1)) * GREATEST(moq_box_case, 1)
            END as recommended_order_qty_constrained,
            
            -- Enhanced review flags including returns
            ARRAY_TO_STRING(ARRAY(
                SELECT flag FROM UNNEST([
                    IF(coverage_percentage > 150, 'Overstocked', NULL),
                    IF(units_sold_current_period = 0 AND units_sold_last_year = 0, 'No sales history', NULL),
                    IF(sell_through_percentage < 10 AND sell_through_percentage > 0, 'Low sell-through', NULL),
                    IF(demand_variability > 1.5, 'High demand variability', NULL),
                    IF(sales_trend = 'Decreasing' AND current_on_hand > weekly_velocity * 8, 'Declining sales with high stock', NULL),
                    IF(is_new_item AND days_with_sales < 30, 'New item - limited history', NULL),
                    IF(yoy_growth_pct < -50 AND current_on_hand > 0, 'Significant YoY decline', NULL),
                    IF(inventory_value > 1000 AND units_sold_last_30d = 0, 'Dead stock risk - high value', NULL),
                    IF(margin_percentage < 20 AND margin_percentage > 0, 'Low margin item', NULL),
                    IF(is_seasonal AND current_on_hand > expected_demand * 0.5, 'Seasonal item with high stock', NULL),
                    IF(moq_box_case > weekly_velocity * 12, 'MOQ exceeds 12 weeks supply', NULL),
                    IF(days_with_sales > 0 AND days_with_sales < 10, 'Sporadic sales pattern', NULL),
                    -- Returns-specific flags
                    IF(return_rate_pct > 15, CONCAT('High return rate (', CAST(ROUND(return_rate_pct, 1) AS STRING), '%)'), NULL),
                    IF(return_rate_pct > 8 AND return_rate_pct <= 15, CONCAT('Moderate return rate (', CAST(ROUND(return_rate_pct, 1) AS STRING), '%)'), NULL),
                    IF(return_count_30d > 5, CONCAT('High return frequency (', CAST(return_count_30d AS STRING), ' returns)'), NULL),
                    IF(return_rate_pct > 8 AND coverage_percentage > 100, 'High returns with excess inventory', NULL)
                ]) AS flag
                WHERE flag IS NOT NULL
            ), ', ') as review_flags,
            
            -- Action group with returns consideration
            CASE 
                WHEN risk_level IN ('Critical', 'High') AND NOT (is_new_item AND days_with_sales < 30) THEN 'Urgent Reorders'
                WHEN risk_level = 'Medium' AND sales_trend != 'Decreasing' THEN 'Monitoring'
                WHEN coverage_percentage > 150 OR (units_sold_current_period = 0 AND units_sold_last_year = 0) THEN 'Review Required'
                WHEN sell_through_percentage < 10 OR demand_variability > 1.5 THEN 'Review Required'
                WHEN inventory_value > 1000 AND units_sold_last_30d = 0 THEN 'Review Required'
                WHEN return_rate_pct > 8 THEN 'Review Required'  -- Returns trigger review
                WHEN return_count_30d > 5 THEN 'Review Required'  -- High return frequency
                ELSE 'Adequate'
            END as action_group
            
        FROM weighting_calcs
    )
    """


# Example usage function
def apply_weighting_to_results(query_results: list) -> list:
    """
    Apply weighting logic to query results including returns analysis
    
    Args:
        query_results: List of dictionaries containing query results
        
    Returns:
        Enhanced results with weighting calculations and returns analysis
    """
    calculator = WeightingCalculator()
    enhanced_results = []
    
    for row in query_results:
        try:
            # Create metrics object from row data
            metrics = CoverageMetrics(
                on_hand_units=row.get('current_on_hand', row.get('oh_units', 0)),
                units_on_order=row.get('units_on_order', 0),
                forecasted_units=row.get('forecast_units'),
                current_period_sales=row.get('units_sold_30d', row.get('units_sold_2025', 0)),
                last_year_sales=row.get('units_sold_last_year', 0),
                sales_value=row.get('revenue_30d', row.get('revenue_2025', 0)),
                margin_percentage=row.get('margin_pct', 0),
                sell_through_percentage=row.get('sell_through_pct', 0),
                mog=row.get('moq', 1),
                box_per_case=row.get('box_per_case', 1),
                is_active=row.get('is_active', True),
                # Additional metrics
                demand_variability=row.get('demand_variability', 0),
                sales_trend=row.get('sales_trend', 'Stable'),
                yoy_growth_pct=row.get('yoy_growth_pct', 0),
                is_new_item=row.get('is_new_item', False),
                is_seasonal=row.get('is_seasonal', False),
                days_with_sales=row.get('days_with_sales_2025', row.get('days_with_sales', 0)),
                inventory_value=row.get('inventory_value', 0),
                units_sold_last_7d=row.get('units_sold_7d', row.get('units_sold_last_7d', 0)),
                units_sold_prev_7d=row.get('units_sold_prev_7d', 0),
                # Returns metrics
                return_count_30d=row.get('return_count_30d', 0),
                return_days_30d=row.get('return_days_30d', 0),
                return_rate_pct=row.get('return_rate_pct', 0)
            )
            
            # Calculate weighting
            weighting_results = calculator.calculate_coverage_analysis(metrics)
            
            # Merge with original row
            enhanced_row = {**row, **weighting_results}
            enhanced_results.append(enhanced_row)
            
        except Exception as e:
            logger.error(f"Error processing SKU {row.get('sku_id', 'unknown')}: {e}")
            enhanced_results.append({**row, 'weighting_error': str(e)})
    
    return enhanced_results


def extract_moq_from_description(sku_description2: str) -> int:
    """
    Extract MOQ/Box Case from sku_description2 field
    Pattern: MO#[number] where number is both MOQ and box case
    
    Args:
        sku_description2: The description field containing MOQ info
        
    Returns:
        MOQ value (defaults to 1 if not found)
    """
    import re
    
    if not sku_description2:
        return 1
        
    # Look for pattern MO# followed by digits
    match = re.search(r'MO#\s*(\d+)', sku_description2)
    if match:
        return int(match.group(1))
    
    return 1
