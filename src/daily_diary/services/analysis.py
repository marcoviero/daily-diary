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
    - Sleep disruption factors (cat, etc.)
    """
    
    def __init__(self, storage: Optional[DiaryStorage] = None, use_db: bool = True):
        self.storage = storage or DiaryStorage()
        self.use_db = use_db
    
    def build_dataframe(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        min_days: int = 7,
    ) -> pd.DataFrame:
        """
        Build a DataFrame from diary data for analysis.
        
        Uses SQLite for comprehensive data if available, falls back to JSON.
        Each row is a day, columns are features.
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=90)
        
        # Try SQLite first for comprehensive data
        if self.use_db:
            try:
                from .database import AnalyticsDB
                with AnalyticsDB() as db:
                    df = db.get_analysis_data(start_date, end_date)
                    if not df.empty and len(df) >= min_days:
                        df['date'] = pd.to_datetime(df['entry_date'])
                        df = df.set_index('date').sort_index()
                        
                        # Add derived columns
                        df['day_of_week'] = df.index.dayofweek
                        df['is_weekend'] = df['day_of_week'] >= 5
                        
                        # Add lagged features
                        for col in ['total_activity_minutes', 'total_elevation_m', 
                                    'total_alcohol_units', 'sleep_score', 'total_sleep_minutes',
                                    'total_caffeine_mg', 'pressure_hpa']:
                            if col in df.columns:
                                df[f'{col}_prev_day'] = df[col].shift(1)
                        
                        return df
            except Exception as e:
                print(f"SQLite analysis failed, falling back to JSON: {e}")
        
        # Fallback to JSON
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
                'temp_avg_c': w.temp_avg_c,
                'temp_high_c': w.temp_high_c,
                'temp_low_c': w.temp_low_c,
                'pressure_hpa': w.pressure_hpa,
                'humidity_percent': w.humidity_percent,
                'wind_speed_kmh': w.wind_speed_kmh,
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
            ('pressure_change', 'Pressure Change (from yesterday)'),
            ('temp_avg_c', 'Average Temperature'),
            ('humidity_percent', 'Humidity'),
            ('sleep_score', 'Sleep Score'),
            ('total_sleep_hours', 'Total Sleep Duration'),
            ('total_sleep_minutes', 'Total Sleep (minutes)'),
            ('deep_sleep_hours', 'Deep Sleep Duration'),
            ('hrv_average', 'Heart Rate Variability'),
            ('total_activity_minutes', 'Exercise Duration'),
            ('elevation_gain', 'Climbing (elevation)'),
            ('total_elevation_m', 'Total Elevation'),
            ('avg_heart_rate', 'Average Exercise HR'),
            ('alcohol_units', 'Alcohol Consumption'),
            ('total_alcohol_units', 'Total Alcohol Units'),
            ('total_caffeine_mg', 'Caffeine (mg)'),
            ('stress_level', 'Stress Level'),
            ('energy_level', 'Energy Level'),
            ('total_activity_minutes_prev_day', 'Previous Day Exercise'),
            ('alcohol_units_prev_day', 'Previous Day Alcohol'),
            ('total_alcohol_units_prev_day', 'Previous Day Alcohol'),
            ('sleep_score_prev_day', 'Previous Night Sleep Score'),
            ('pressure_hpa_prev_day', 'Previous Day Pressure'),
            ('total_caffeine_mg_prev_day', 'Previous Day Caffeine'),
        ]
        
        binary_factors = [
            ('is_weekend', 'Weekend'),
            ('alcohol_consumed', 'Any Alcohol'),
            ('caffeine_consumed', 'Caffeine'),
            ('has_incidents', 'Had Incident'),
            ('cat_in_room', 'Cat Slept in Room'),
            ('cat_woke_me', 'Cat Woke Me Up'),
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
        
        # Count unique dates (not rows, in case of duplicates)
        unique_dates = df.index.nunique() if hasattr(df.index, 'nunique') else len(df)
        
        # Calculate symptom rate using available columns
        # has_headache is 1/0, symptom_count is the count, has_symptoms from JSON
        if 'has_headache' in df.columns:
            days_with_symptoms = int(df['has_headache'].sum())
            symptom_rate = float(df['has_headache'].mean())
        elif 'has_symptoms' in df.columns:
            days_with_symptoms = int(df['has_symptoms'].sum())
            symptom_rate = float(df['has_symptoms'].mean())
        elif 'symptom_count' in df.columns:
            days_with_symptoms = int((df['symptom_count'] > 0).sum())
            symptom_rate = float((df['symptom_count'] > 0).mean())
        else:
            days_with_symptoms = 0
            symptom_rate = 0
        
        # Only calculate means for non-null values
        avg_wellbeing = None
        if 'overall_wellbeing' in df.columns:
            valid = df['overall_wellbeing'].dropna()
            if len(valid) > 0:
                avg_wellbeing = float(valid.mean())
        
        avg_sleep_score = None
        if 'sleep_score' in df.columns:
            valid = df['sleep_score'].dropna()
            if len(valid) > 0:
                avg_sleep_score = float(valid.mean())
        
        stats_dict = {
            'period_days': unique_dates,
            'start_date': df.index.min().strftime('%Y-%m-%d') if len(df) > 0 else None,
            'end_date': df.index.max().strftime('%Y-%m-%d') if len(df) > 0 else None,
            'days_with_symptoms': days_with_symptoms,
            'symptom_rate': symptom_rate,
            'avg_wellbeing': avg_wellbeing,
            'avg_sleep_score': avg_sleep_score,
            'total_activity_hours': float(df['total_activity_minutes'].sum() / 60) if 'total_activity_minutes' in df.columns else 0,
            'total_elevation_m': float(df['total_elevation_m'].sum()) if 'total_elevation_m' in df.columns else 0,
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
        
        # Time series of symptom severity and wellbeing
        # Use None for missing values instead of 0 so charts can skip them
        severity_col = None
        if 'worst_symptom_severity' in df.columns:
            severity_col = 'worst_symptom_severity'
        elif 'has_headache' in df.columns:
            severity_col = 'has_headache'
        
        if severity_col:
            # Convert to list, replacing NaN with None for JSON
            severity_data = df[severity_col].where(pd.notna(df[severity_col]), None).tolist()
            
            wellbeing_data = []
            if 'overall_wellbeing' in df.columns:
                wellbeing_data = df['overall_wellbeing'].where(pd.notna(df['overall_wellbeing']), None).tolist()
            
            sleep_score_data = []
            if 'sleep_score' in df.columns:
                sleep_score_data = df['sleep_score'].where(pd.notna(df['sleep_score']), None).tolist()
            
            charts['symptom_timeline'] = {
                'dates': df.index.strftime('%Y-%m-%d').tolist(),
                'severity': severity_data,
                'wellbeing': wellbeing_data,
                'sleep_score': sleep_score_data,
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
    
    def analyze_medication_effectiveness(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[dict]:
        """
        Analyze medication effectiveness for rescue medications.
        
        For each medication found in the data:
        - Count times taken
        - Compare headache severity on days with/without medication
        - Look for same-day relief patterns (if timestamps available)
        
        Returns list of medication analysis results.
        """
        from .database import AnalyticsDB
        
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=90)
        
        results = []
        
        try:
            with AnalyticsDB() as db:
                # Get all medications
                meds_df = pd.read_sql("""
                    SELECT 
                        entry_date,
                        name,
                        dosage,
                        time_taken,
                        purpose as reason
                    FROM medications
                    WHERE entry_date >= ? AND entry_date <= ?
                    ORDER BY entry_date, time_taken
                """, db.conn, params=[start_date, end_date])
                
                if meds_df.empty:
                    return []
                
                # Get all symptoms (focus on headaches)
                symptoms_df = pd.read_sql("""
                    SELECT 
                        entry_date,
                        symptom_type,
                        severity,
                        onset_time
                    FROM symptoms
                    WHERE entry_date >= ? AND entry_date <= ?
                    ORDER BY entry_date, onset_time
                """, db.conn, params=[start_date, end_date])
                
                # Get all dates in range for baseline comparison
                all_dates_df = pd.read_sql("""
                    SELECT DISTINCT entry_date 
                    FROM daily_summary
                    WHERE entry_date >= ? AND entry_date <= ?
                """, db.conn, params=[start_date, end_date])
                
                all_dates = set(all_dates_df['entry_date'].tolist()) if not all_dates_df.empty else set()
                
                # Analyze each unique medication
                for med_name in meds_df['name'].str.lower().unique():
                    med_rows = meds_df[meds_df['name'].str.lower() == med_name]
                    
                    # Days this medication was taken
                    med_dates = set(med_rows['entry_date'].tolist())
                    times_taken = len(med_rows)
                    
                    # Get typical dosage
                    dosages = med_rows['dosage'].dropna().unique()
                    typical_dosage = dosages[0] if len(dosages) > 0 else None
                    
                    # Headache analysis
                    headache_types = ['headache', 'headache_neuralgiaform', 'neuralgiaform_headache']
                    headaches = symptoms_df[symptoms_df['symptom_type'].str.lower().isin(headache_types)]
                    
                    # Severity on med days vs non-med days
                    headache_on_med_days = headaches[headaches['entry_date'].isin(med_dates)]
                    headache_on_other_days = headaches[~headaches['entry_date'].isin(med_dates)]
                    
                    avg_severity_med_days = headache_on_med_days['severity'].mean() if len(headache_on_med_days) > 0 else None
                    avg_severity_other_days = headache_on_other_days['severity'].mean() if len(headache_on_other_days) > 0 else None
                    
                    # Days with headache
                    headache_dates = set(headaches['entry_date'].tolist())
                    days_with_med_and_headache = len(med_dates & headache_dates)
                    
                    # Calculate response (did they take it for headache and was severity lower than baseline?)
                    effectiveness_notes = []
                    
                    if times_taken >= 3:  # Need enough data points
                        if avg_severity_med_days is not None and avg_severity_other_days is not None:
                            if avg_severity_med_days < avg_severity_other_days:
                                diff = avg_severity_other_days - avg_severity_med_days
                                effectiveness_notes.append(
                                    f"Headaches on {med_name.title()} days average {diff:.1f} points lower severity"
                                )
                            elif avg_severity_med_days > avg_severity_other_days:
                                # This is expected - you take rescue meds for worse headaches
                                effectiveness_notes.append(
                                    f"Taken for more severe headaches (avg {avg_severity_med_days:.1f}/10 vs baseline {avg_severity_other_days:.1f}/10)"
                                )
                    
                    # Same-day relief analysis (if we have timestamps)
                    relief_cases = 0
                    no_relief_cases = 0
                    
                    for med_date in med_dates:
                        day_meds = med_rows[med_rows['entry_date'] == med_date]
                        day_headaches = headache_on_med_days[headache_on_med_days['entry_date'] == med_date]
                        
                        if len(day_headaches) >= 2:
                            # Multiple symptom entries - check if severity decreased
                            severities = day_headaches.sort_values('onset_time')['severity'].tolist()
                            if len(severities) >= 2 and severities[-1] < severities[0]:
                                relief_cases += 1
                            elif len(severities) >= 2 and severities[-1] >= severities[0]:
                                no_relief_cases += 1
                    
                    if relief_cases + no_relief_cases > 0:
                        relief_rate = relief_cases / (relief_cases + no_relief_cases) * 100
                        effectiveness_notes.append(
                            f"Same-day relief observed {relief_rate:.0f}% of tracked cases ({relief_cases}/{relief_cases + no_relief_cases})"
                        )
                    
                    results.append({
                        'medication': med_name.title(),
                        'dosage': typical_dosage,
                        'times_taken': times_taken,
                        'days_taken': len(med_dates),
                        'days_with_headache': days_with_med_and_headache,
                        'avg_severity_med_days': round(avg_severity_med_days, 1) if avg_severity_med_days else None,
                        'avg_severity_baseline': round(avg_severity_other_days, 1) if avg_severity_other_days else None,
                        'effectiveness_notes': effectiveness_notes,
                        'data_quality': 'good' if times_taken >= 5 else 'limited' if times_taken >= 3 else 'insufficient',
                    })
                
                # Sort by times taken (most used first)
                results.sort(key=lambda x: x['times_taken'], reverse=True)
                
        except Exception as e:
            print(f"Medication analysis error: {e}")
        
        return results
    
    def analyze_lag_correlations(
        self,
        target: str = 'has_headache',
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        max_lag_days: int = 3,
    ) -> list[dict]:
        """
        Analyze correlations with time delays.
        
        Useful for understanding delayed effects like:
        - Medication effects (may take 1-2 days)
        - Exercise benefits (next-day effects)
        - Sleep debt accumulation
        - Dietary impacts
        
        Returns list of factors with their optimal lag and correlation strength.
        """
        df = self.build_dataframe(start_date, end_date)
        
        if df.empty or target not in df.columns:
            return []
        
        # Factors to analyze with lags
        factors = [
            ('total_activity_minutes', 'Exercise Duration'),
            ('total_elevation_m', 'Elevation Gain'),
            ('sleep_score', 'Sleep Score'),
            ('total_sleep_minutes', 'Sleep Duration'),
            ('total_caffeine_mg', 'Caffeine Intake'),
            ('total_alcohol_units', 'Alcohol Units'),
            ('pressure_hpa', 'Barometric Pressure'),
            ('overall_wellbeing', 'Wellbeing Score'),
            ('total_calories', 'Calorie Intake'),
        ]
        
        results = []
        
        for col, name in factors:
            if col not in df.columns:
                continue
            
            best_lag = 0
            best_r = 0
            best_p = 1.0
            best_n = 0
            lag_results = []
            
            # Test each lag (0 = same day, 1 = previous day, etc.)
            for lag in range(max_lag_days + 1):
                if lag == 0:
                    shifted = df[col]
                else:
                    shifted = df[col].shift(lag)
                
                # Get paired data
                mask = shifted.notna() & df[target].notna()
                x = shifted[mask]
                y = df.loc[mask, target]
                
                if len(x) < 10:  # Need enough samples
                    continue
                
                try:
                    r, p = stats.pearsonr(x, y)
                    lag_results.append({
                        'lag': lag,
                        'r': r,
                        'p': p,
                        'n': len(x)
                    })
                    
                    # Track strongest significant correlation
                    if p < 0.1 and abs(r) > abs(best_r):  # Use p < 0.1 for detection
                        best_lag = lag
                        best_r = r
                        best_p = p
                        best_n = len(x)
                except:
                    continue
            
            if best_n >= 10 and best_p < 0.1:
                lag_desc = {
                    0: 'same day',
                    1: 'previous day',
                    2: '2 days prior',
                    3: '3 days prior'
                }
                
                interpretation = self._interpret_lag_correlation(name, best_r, best_p, best_lag, target)
                
                results.append({
                    'factor': name,
                    'optimal_lag': best_lag,
                    'lag_description': lag_desc.get(best_lag, f'{best_lag} days prior'),
                    'correlation': round(best_r, 3),
                    'p_value': round(best_p, 4),
                    'n_samples': best_n,
                    'is_significant': best_p < 0.05,
                    'strength': self._get_strength(best_r),
                    'interpretation': interpretation,
                    'all_lags': lag_results,
                })
        
        # Sort by significance then strength
        results.sort(key=lambda x: (-int(x['is_significant']), -abs(x['correlation'])))
        
        return results
    
    def _get_strength(self, r: float) -> str:
        """Get correlation strength description."""
        r = abs(r)
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
    
    def _interpret_lag_correlation(
        self,
        factor: str,
        r: float,
        p: float,
        lag: int,
        target: str
    ) -> str:
        """Generate interpretation for lag correlation."""
        if p >= 0.1:
            return f"No clear delayed relationship found."
        
        strength = self._get_strength(r)
        
        if lag == 0:
            timing = "on the same day"
        elif lag == 1:
            timing = "the following day"
        else:
            timing = f"{lag} days later"
        
        if "sleep" in factor.lower():
            if r < 0:
                return f"Better sleep is associated with fewer symptoms {timing} ({strength} effect)."
            else:
                return f"Sleep patterns show a relationship with symptoms {timing}."
        elif "exercise" in factor.lower() or "activity" in factor.lower():
            if r < 0:
                return f"More activity appears to reduce symptoms {timing} ({strength} effect)."
            else:
                return f"Higher activity levels correlate with symptoms {timing}. Consider if this reflects overexertion."
        elif "caffeine" in factor.lower():
            if r > 0:
                return f"Higher caffeine intake is associated with more symptoms {timing}. Consider reducing intake."
            else:
                return f"Caffeine shows a {strength} protective relationship {timing}."
        elif "alcohol" in factor.lower():
            if r > 0:
                return f"Alcohol consumption correlates with worse symptoms {timing}."
            else:
                return f"Alcohol shows unexpected negative correlation {timing}."
        elif "pressure" in factor.lower():
            if r < 0:
                return f"Lower pressure is associated with worse symptoms {timing}. You may be weather-sensitive."
            else:
                return f"Higher pressure correlates with symptoms {timing}."
        elif "wellbeing" in factor.lower():
            return f"Wellbeing shows a {strength} {'' if r < 0 else 'inverse '}correlation with symptoms {timing}."
        else:
            return f"{factor} shows a {strength} {'protective' if r < 0 else 'risk'} correlation {timing}."
    
    def get_actionable_insights(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[dict]:
        """
        Generate actionable health insights based on the data.
        
        Returns prioritized list of insights with specific recommendations.
        """
        df = self.build_dataframe(start_date, end_date)
        
        if df.empty:
            return []
        
        insights = []
        
        # Determine symptom column
        symptom_col = 'has_headache' if 'has_headache' in df.columns else 'has_symptoms' if 'has_symptoms' in df.columns else None
        
        if not symptom_col:
            return []
        
        # 1. Sleep quality impact
        if 'sleep_score' in df.columns:
            low_sleep = df[df['sleep_score'] < 70]
            high_sleep = df[df['sleep_score'] >= 70]
            
            if len(low_sleep) >= 5 and len(high_sleep) >= 5:
                low_sleep_symptom_rate = low_sleep[symptom_col].mean()
                high_sleep_symptom_rate = high_sleep[symptom_col].mean()
                
                if low_sleep_symptom_rate > high_sleep_symptom_rate * 1.3:  # 30% higher
                    diff = (low_sleep_symptom_rate - high_sleep_symptom_rate) * 100
                    insights.append({
                        'category': 'Sleep',
                        'priority': 'high',
                        'insight': f'Poor sleep nights (<70 score) have {diff:.0f}% more symptom days',
                        'recommendation': 'Focus on sleep hygiene. Consider consistent bedtime, limiting screens before bed, and avoiding late caffeine.',
                        'data_quality': 'good' if len(low_sleep) >= 10 else 'limited',
                    })
        
        # 2. Weekend patterns
        if 'is_weekend' in df.columns:
            weekend = df[df['is_weekend'] == True]
            weekday = df[df['is_weekend'] == False]
            
            if len(weekend) >= 5 and len(weekday) >= 10:
                weekend_rate = weekend[symptom_col].mean()
                weekday_rate = weekday[symptom_col].mean()
                
                if abs(weekend_rate - weekday_rate) > 0.15:  # 15% difference
                    if weekend_rate > weekday_rate:
                        insights.append({
                            'category': 'Lifestyle',
                            'priority': 'medium',
                            'insight': f'Weekend symptom rate is higher ({weekend_rate*100:.0f}% vs {weekday_rate*100:.0f}%)',
                            'recommendation': 'Weekend triggers might include sleep schedule changes, alcohol, or different activities. Try maintaining consistent routines.',
                            'data_quality': 'good',
                        })
                    else:
                        insights.append({
                            'category': 'Lifestyle',
                            'priority': 'medium',
                            'insight': f'Weekday symptom rate is higher ({weekday_rate*100:.0f}% vs {weekend_rate*100:.0f}%)',
                            'recommendation': 'Work stress, screen time, or weekday habits may be contributing. Consider stress management techniques.',
                            'data_quality': 'good',
                        })
        
        # 3. Caffeine impact (with lag)
        if 'total_caffeine_mg' in df.columns:
            df['caffeine_prev'] = df['total_caffeine_mg'].shift(1)
            high_caffeine = df[df['caffeine_prev'] > 200]  # >200mg previous day
            low_caffeine = df[df['caffeine_prev'] <= 200]
            
            if len(high_caffeine) >= 5 and len(low_caffeine) >= 5:
                high_rate = high_caffeine[symptom_col].mean()
                low_rate = low_caffeine[symptom_col].mean()
                
                if high_rate > low_rate * 1.2:
                    insights.append({
                        'category': 'Diet',
                        'priority': 'medium',
                        'insight': f'High caffeine days (>200mg) are followed by more symptoms',
                        'recommendation': 'Consider limiting caffeine, especially after noon. Gradual reduction prevents withdrawal headaches.',
                        'data_quality': 'good' if len(high_caffeine) >= 10 else 'limited',
                    })
        
        # 4. Exercise benefits
        if 'total_activity_minutes' in df.columns:
            active = df[df['total_activity_minutes'] >= 30]
            inactive = df[df['total_activity_minutes'] < 30]
            
            if len(active) >= 5 and len(inactive) >= 5:
                active_rate = active[symptom_col].mean()
                inactive_rate = inactive[symptom_col].mean()
                
                if inactive_rate > active_rate * 1.2:
                    insights.append({
                        'category': 'Exercise',
                        'priority': 'medium',
                        'insight': f'Days with 30+ min activity have fewer symptoms',
                        'recommendation': 'Regular moderate exercise may help prevent symptoms. Even walking counts!',
                        'data_quality': 'good' if len(active) >= 10 else 'limited',
                    })
        
        # 5. Weather sensitivity
        if 'pressure_hpa' in df.columns:
            valid_pressure = df[df['pressure_hpa'].notna()]
            if len(valid_pressure) >= 20:
                low_p = valid_pressure[valid_pressure['pressure_hpa'] < valid_pressure['pressure_hpa'].quantile(0.25)]
                high_p = valid_pressure[valid_pressure['pressure_hpa'] > valid_pressure['pressure_hpa'].quantile(0.75)]
                
                if len(low_p) >= 5 and len(high_p) >= 5:
                    low_p_rate = low_p[symptom_col].mean()
                    high_p_rate = high_p[symptom_col].mean()
                    
                    if low_p_rate > high_p_rate * 1.3:
                        insights.append({
                            'category': 'Weather',
                            'priority': 'low',
                            'insight': f'Low pressure days show more symptoms ({low_p_rate*100:.0f}% vs {high_p_rate*100:.0f}%)',
                            'recommendation': 'You may be weather-sensitive. Consider preemptive measures when storms approach.',
                            'data_quality': 'good',
                        })
        
        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        insights.sort(key=lambda x: priority_order.get(x['priority'], 3))
        
        return insights
