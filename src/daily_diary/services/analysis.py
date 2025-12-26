"""Analysis service for symptom correlations."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from scipy import stats

from ..models.entry import DiaryEntry
from ..models.health import SymptomType
from ..services.storage import DiaryStorage


@dataclass
class CorrelationResult:
    """Result of a correlation analysis."""
    factor: str
    correlation: float  # Pearson r or point-biserial r
    p_value: float
    n_samples: int
    interpretation: str
    
    @property
    def is_significant(self) -> bool:
        return self.p_value < 0.05
    
    @property
    def strength(self) -> str:
        r = abs(self.correlation)
        if r < 0.1:
            return "negligible"
        elif r < 0.3:
            return "weak"
        elif r < 0.5:
            return "moderate"
        elif r < 0.7:
            return "strong"
        else:
            return "very strong"
    
    @property
    def direction(self) -> str:
        if self.correlation > 0:
            return "positive"
        elif self.correlation < 0:
            return "negative"
        return "none"


@dataclass
class SymptomPattern:
    """Pattern detected in symptom occurrence."""
    pattern_type: str  # 'day_of_week', 'time_of_day', 'weather', etc.
    description: str
    frequency: float  # Percentage or count
    details: dict


class AnalysisService:
    """
    Service for analyzing diary entries and finding correlations.
    
    Looks for relationships between symptoms and:
    - Weather (pressure, temperature, humidity)
    - Sleep quality and duration
    - Exercise intensity and timing
    - Food and alcohol consumption
    - Day of week patterns
    - Previous day's activities
    """
    
    def __init__(self, storage: Optional[DiaryStorage] = None):
        self.storage = storage or DiaryStorage()
    
    def build_dataframe(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        min_days: int = 7,
    ) -> pd.DataFrame:
        """
        Build a DataFrame from diary entries for analysis.
        
        Each row is a day, columns are features.
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=90)
        
        with self.storage as storage:
            entries = storage.get_entries_in_range(start_date, end_date)
        
        if len(entries) < min_days:
            return pd.DataFrame()
        
        rows = []
        for entry in entries:
            row = self._entry_to_row(entry)
            rows.append(row)
        
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
        
        # Add lagged features (previous day)
        for col in ['total_activity_minutes', 'elevation_gain', 'alcohol_units', 
                    'sleep_score', 'total_sleep_hours']:
            if col in df.columns:
                df[f'{col}_prev_day'] = df[col].shift(1)
        
        return df
    
    def _entry_to_row(self, entry: DiaryEntry) -> dict:
        """Convert a diary entry to a flat dictionary for DataFrame."""
        row = {
            'date': entry.entry_date,
            'day_of_week': entry.entry_date.weekday(),
            'is_weekend': entry.entry_date.weekday() >= 5,
            
            # Wellbeing
            'overall_wellbeing': entry.overall_wellbeing,
            'energy_level': entry.energy_level,
            'stress_level': entry.stress_level,
            
            # Symptoms
            'has_symptoms': entry.has_symptoms,
            'symptom_count': len(entry.symptoms),
            'worst_symptom_severity': entry.worst_symptom_severity,
            'has_headache': any(
                s.type in (SymptomType.HEADACHE, SymptomType.HEADACHE_NEURALGIAFORM)
                for s in entry.symptoms
            ),
            'has_neuralgiaform': any(
                s.type == SymptomType.HEADACHE_NEURALGIAFORM
                for s in entry.symptoms
            ),
            
            # Incidents
            'has_incidents': entry.has_incidents,
            'incident_count': len(entry.incidents),
            
            # Meals
            'alcohol_consumed': entry.alcohol_consumed,
            'alcohol_units': entry.total_alcohol_units,
            'caffeine_consumed': any(m.contains_caffeine for m in entry.meals),
        }
        
        # Weather
        if entry.integrations.weather:
            w = entry.integrations.weather
            row.update({
                'temp_avg_f': w.temp_avg_f,
                'temp_high_f': w.temp_high_f,
                'temp_low_f': w.temp_low_f,
                'pressure_hpa': w.pressure_hpa,
                'humidity_percent': w.humidity_percent,
                'wind_speed_mph': w.wind_speed_mph,
            })
        
        # Activity
        row['total_activity_minutes'] = entry.integrations.total_activity_minutes
        row['elevation_gain'] = entry.integrations.total_elevation_gain
        if entry.integrations.activities:
            # Average intensity metrics
            hrs = [a.average_heart_rate for a in entry.integrations.activities if a.average_heart_rate]
            row['avg_heart_rate'] = sum(hrs) / len(hrs) if hrs else None
            powers = [a.average_power_watts for a in entry.integrations.activities if a.average_power_watts]
            row['avg_power'] = sum(powers) / len(powers) if powers else None
        
        # Sleep
        if entry.integrations.sleep:
            s = entry.integrations.sleep
            row.update({
                'sleep_score': s.sleep_score,
                'total_sleep_hours': (s.total_sleep_minutes or 0) / 60,
                'deep_sleep_hours': (s.deep_sleep_minutes or 0) / 60,
                'rem_sleep_hours': (s.rem_sleep_minutes or 0) / 60,
                'hrv_average': s.hrv_average,
                'lowest_hr_sleep': s.lowest_heart_rate,
            })
        
        return row
    
    def analyze_symptom_correlations(
        self,
        target: str = 'worst_symptom_severity',
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[CorrelationResult]:
        """
        Analyze correlations between symptoms and various factors.
        
        Args:
            target: The symptom metric to correlate against
            start_date: Start of analysis period
            end_date: End of analysis period
            
        Returns:
            List of correlation results, sorted by absolute correlation strength
        """
        df = self.build_dataframe(start_date, end_date)
        
        if df.empty or target not in df.columns:
            return []
        
        results = []
        
        # Factors to correlate against
        continuous_factors = [
            ('pressure_hpa', 'Barometric Pressure'),
            ('temp_avg_f', 'Average Temperature'),
            ('humidity_percent', 'Humidity'),
            ('sleep_score', 'Sleep Score'),
            ('total_sleep_hours', 'Total Sleep Duration'),
            ('deep_sleep_hours', 'Deep Sleep Duration'),
            ('hrv_average', 'Heart Rate Variability'),
            ('total_activity_minutes', 'Exercise Duration'),
            ('elevation_gain', 'Climbing (elevation)'),
            ('avg_heart_rate', 'Average Exercise HR'),
            ('alcohol_units', 'Alcohol Consumption'),
            ('stress_level', 'Stress Level'),
            ('energy_level', 'Energy Level'),
            ('total_activity_minutes_prev_day', 'Previous Day Exercise'),
            ('alcohol_units_prev_day', 'Previous Day Alcohol'),
            ('sleep_score_prev_day', 'Previous Night Sleep Score'),
        ]
        
        binary_factors = [
            ('is_weekend', 'Weekend'),
            ('alcohol_consumed', 'Any Alcohol'),
            ('caffeine_consumed', 'Caffeine'),
            ('has_incidents', 'Had Incident'),
        ]
        
        target_series = df[target].dropna()
        
        # Continuous correlations (Pearson)
        for col, name in continuous_factors:
            if col not in df.columns:
                continue
            
            # Get paired data (both non-null)
            mask = df[col].notna() & df[target].notna()
            x = df.loc[mask, col]
            y = df.loc[mask, target]
            
            if len(x) < 5:
                continue
            
            try:
                r, p = stats.pearsonr(x, y)
                results.append(CorrelationResult(
                    factor=name,
                    correlation=r,
                    p_value=p,
                    n_samples=len(x),
                    interpretation=self._interpret_correlation(name, r, p, target),
                ))
            except Exception:
                continue
        
        # Binary correlations (point-biserial)
        for col, name in binary_factors:
            if col not in df.columns:
                continue
            
            mask = df[col].notna() & df[target].notna()
            x = df.loc[mask, col].astype(int)
            y = df.loc[mask, target]
            
            if len(x) < 5 or x.nunique() < 2:
                continue
            
            try:
                r, p = stats.pointbiserialr(x, y)
                results.append(CorrelationResult(
                    factor=name,
                    correlation=r,
                    p_value=p,
                    n_samples=len(x),
                    interpretation=self._interpret_correlation(name, r, p, target),
                ))
            except Exception:
                continue
        
        # Sort by absolute correlation strength
        results.sort(key=lambda x: abs(x.correlation), reverse=True)
        
        return results
    
    def _interpret_correlation(
        self,
        factor: str,
        r: float,
        p: float,
        target: str,
    ) -> str:
        """Generate human-readable interpretation of correlation."""
        if p >= 0.05:
            return f"No significant relationship found between {factor} and symptoms."
        
        strength = "weak" if abs(r) < 0.3 else "moderate" if abs(r) < 0.5 else "strong"
        direction = "higher" if r > 0 else "lower"
        
        # Custom interpretations for known factors
        if "pressure" in factor.lower():
            if r < 0:
                return f"Lower barometric pressure is associated with worse symptoms ({strength} correlation). Consider monitoring pressure changes."
            else:
                return f"Higher barometric pressure is associated with worse symptoms ({strength} correlation)."
        
        if "sleep" in factor.lower():
            if r < 0:
                return f"Better sleep is associated with fewer/milder symptoms ({strength} correlation). Prioritize sleep quality."
            else:
                return f"Interestingly, higher sleep scores correlate with more symptoms. This may indicate sleeping more when unwell."
        
        if "alcohol" in factor.lower():
            if r > 0:
                return f"Alcohol consumption is associated with worse symptoms ({strength} correlation). Consider reducing intake."
        
        if "exercise" in factor.lower() or "activity" in factor.lower():
            if r < 0:
                return f"More exercise is associated with fewer symptoms ({strength} correlation). Keep up the activity!"
            else:
                return f"More exercise correlates with more symptoms. This might indicate overexertion as a trigger."
        
        return f"{factor} shows a {strength} {direction} correlation with symptoms."
    
    def find_symptom_patterns(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[SymptomPattern]:
        """Find patterns in symptom occurrence."""
        df = self.build_dataframe(start_date, end_date)
        
        if df.empty:
            return []
        
        patterns = []
        
        # Day of week patterns
        if 'has_symptoms' in df.columns and df['has_symptoms'].sum() > 0:
            dow_symptoms = df.groupby('day_of_week')['has_symptoms'].mean()
            worst_day = dow_symptoms.idxmax()
            best_day = dow_symptoms.idxmin()
            
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            if dow_symptoms.max() - dow_symptoms.min() > 0.15:
                patterns.append(SymptomPattern(
                    pattern_type='day_of_week',
                    description=f"Symptoms are most common on {day_names[worst_day]}s ({dow_symptoms.max():.0%} of days) "
                               f"and least common on {day_names[best_day]}s ({dow_symptoms.min():.0%} of days).",
                    frequency=dow_symptoms.max(),
                    details={'worst_day': day_names[worst_day], 'best_day': day_names[best_day]},
                ))
        
        # Weekend vs weekday
        if 'is_weekend' in df.columns and 'has_symptoms' in df.columns:
            weekend_rate = df[df['is_weekend']]['has_symptoms'].mean() if df['is_weekend'].sum() > 0 else 0
            weekday_rate = df[~df['is_weekend']]['has_symptoms'].mean() if (~df['is_weekend']).sum() > 0 else 0
            
            if abs(weekend_rate - weekday_rate) > 0.1:
                if weekend_rate > weekday_rate:
                    patterns.append(SymptomPattern(
                        pattern_type='weekend',
                        description=f"Symptoms are more common on weekends ({weekend_rate:.0%}) than weekdays ({weekday_rate:.0%}).",
                        frequency=weekend_rate,
                        details={'weekend_rate': weekend_rate, 'weekday_rate': weekday_rate},
                    ))
                else:
                    patterns.append(SymptomPattern(
                        pattern_type='weekend',
                        description=f"Symptoms are less common on weekends ({weekend_rate:.0%}) than weekdays ({weekday_rate:.0%}).",
                        frequency=weekday_rate,
                        details={'weekend_rate': weekend_rate, 'weekday_rate': weekday_rate},
                    ))
        
        return patterns
    
    def get_summary_stats(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get summary statistics for the analysis period."""
        df = self.build_dataframe(start_date, end_date)
        
        if df.empty:
            return {'error': 'No data available'}
        
        stats_dict = {
            'period_days': len(df),
            'start_date': df.index.min().strftime('%Y-%m-%d'),
            'end_date': df.index.max().strftime('%Y-%m-%d'),
            'days_with_symptoms': int(df['has_symptoms'].sum()) if 'has_symptoms' in df.columns else 0,
            'symptom_rate': float(df['has_symptoms'].mean()) if 'has_symptoms' in df.columns else 0,
            'avg_wellbeing': float(df['overall_wellbeing'].mean()) if 'overall_wellbeing' in df.columns and df['overall_wellbeing'].notna().any() else None,
            'avg_sleep_score': float(df['sleep_score'].mean()) if 'sleep_score' in df.columns and df['sleep_score'].notna().any() else None,
            'total_activity_hours': float(df['total_activity_minutes'].sum() / 60) if 'total_activity_minutes' in df.columns else 0,
            'total_elevation_m': float(df['elevation_gain'].sum()) if 'elevation_gain' in df.columns else 0,
        }
        
        return stats_dict
    
    def generate_chart_data(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Generate data for charts/visualizations."""
        df = self.build_dataframe(start_date, end_date)
        
        if df.empty:
            return {}
        
        charts = {}
        
        # Time series of symptom severity
        if 'worst_symptom_severity' in df.columns:
            charts['symptom_timeline'] = {
                'dates': df.index.strftime('%Y-%m-%d').tolist(),
                'severity': df['worst_symptom_severity'].fillna(0).tolist(),
                'wellbeing': df['overall_wellbeing'].fillna(0).tolist() if 'overall_wellbeing' in df.columns else [],
            }
        
        # Pressure vs symptoms scatter
        if 'pressure_hpa' in df.columns and 'worst_symptom_severity' in df.columns:
            mask = df['pressure_hpa'].notna() & df['worst_symptom_severity'].notna()
            charts['pressure_scatter'] = {
                'pressure': df.loc[mask, 'pressure_hpa'].tolist(),
                'severity': df.loc[mask, 'worst_symptom_severity'].tolist(),
                'dates': df.loc[mask].index.strftime('%Y-%m-%d').tolist(),
            }
        
        # Sleep vs symptoms
        if 'sleep_score' in df.columns and 'worst_symptom_severity' in df.columns:
            mask = df['sleep_score'].notna() & df['worst_symptom_severity'].notna()
            charts['sleep_scatter'] = {
                'sleep_score': df.loc[mask, 'sleep_score'].tolist(),
                'severity': df.loc[mask, 'worst_symptom_severity'].tolist(),
            }
        
        return charts
