-- Daily Diary Analytics Database Schema
-- DuckDB relational database for health tracking analytics
-- 
-- Tables are organized by health domain:
-- - sleep: Oura Ring sleep data
-- - activities: Strava exercise data  
-- - meals: Food intake with nutritional estimates
-- - symptoms: Health symptoms tracking
-- - incidents: Notable health events
-- - weather: Environmental conditions
-- - vitals: Manual measurements
-- - medications: Medication tracking
-- - supplements: Supplement intake
-- - hydration: Fluid intake
-- - daily_summary: Aggregated daily metrics
-- - correlation_cache: Pre-computed correlations

-- =============================================
-- SLEEP TABLE
-- Detailed sleep data from Oura Ring
-- =============================================
CREATE TABLE IF NOT EXISTS sleep (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    
    -- Timing
    bedtime TIMESTAMP,
    wake_time TIMESTAMP,
    
    -- Duration (minutes)
    total_sleep_minutes INTEGER,
    rem_sleep_minutes INTEGER,
    deep_sleep_minutes INTEGER,
    light_sleep_minutes INTEGER,
    awake_minutes INTEGER,
    
    -- Quality scores (0-100)
    sleep_score INTEGER,
    efficiency_percent INTEGER,
    
    -- Physiological
    lowest_heart_rate FLOAT,
    average_heart_rate FLOAT,
    hrv_average FLOAT,
    hrv_max FLOAT,
    respiratory_rate FLOAT,
    body_temperature_delta FLOAT,
    
    -- Readiness
    readiness_score INTEGER,
    restless_periods INTEGER,
    
    -- Source tracking
    source VARCHAR DEFAULT 'oura',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(entry_date, source)
);

-- =============================================
-- ACTIVITIES TABLE
-- Exercise and movement data from Strava
-- =============================================
CREATE TABLE IF NOT EXISTS activities (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    
    -- Basic info
    activity_type VARCHAR NOT NULL,
    name VARCHAR,
    description VARCHAR,
    start_time TIMESTAMP,
    
    -- Duration and distance
    duration_minutes FLOAT,
    distance_km FLOAT,
    elevation_gain_m FLOAT,
    elevation_loss_m FLOAT,
    
    -- Speed
    average_speed_kmh FLOAT,
    max_speed_kmh FLOAT,
    
    -- Heart rate
    average_heart_rate FLOAT,
    max_heart_rate FLOAT,
    heart_rate_zones_json VARCHAR,  -- JSON array
    
    -- Power (cycling)
    average_power_watts FLOAT,
    max_power_watts FLOAT,
    normalized_power_watts FLOAT,
    intensity_factor FLOAT,
    training_stress_score FLOAT,
    
    -- Cadence
    average_cadence FLOAT,
    max_cadence FLOAT,
    
    -- Effort
    suffer_score FLOAT,
    perceived_exertion INTEGER,  -- 1-10 RPE
    calories_burned FLOAT,
    
    -- Weather during activity
    temperature_c FLOAT,
    humidity_percent INTEGER,
    wind_speed_kmh FLOAT,
    
    -- Source tracking
    source VARCHAR DEFAULT 'strava',
    external_id VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- MEALS TABLE
-- Food intake with nutritional breakdown
-- Supports LLM-estimated or manually entered data
-- =============================================
CREATE TABLE IF NOT EXISTS meals (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    
    -- Meal info
    meal_type VARCHAR NOT NULL,  -- breakfast, lunch, dinner, snack, drink
    time_consumed TIME,
    description VARCHAR NOT NULL,
    
    -- Macronutrients
    calories FLOAT,
    protein_g FLOAT,
    carbs_g FLOAT,
    fat_g FLOAT,
    fiber_g FLOAT,
    sugar_g FLOAT,
    sodium_mg FLOAT,
    
    -- Micronutrients (optional)
    vitamin_a_iu FLOAT,
    vitamin_c_mg FLOAT,
    vitamin_d_iu FLOAT,
    calcium_mg FLOAT,
    iron_mg FLOAT,
    potassium_mg FLOAT,
    magnesium_mg FLOAT,
    
    -- Hydration
    water_ml FLOAT,
    
    -- Alcohol tracking
    contains_alcohol BOOLEAN DEFAULT FALSE,
    alcohol_units FLOAT,
    alcohol_type VARCHAR,
    
    -- Caffeine tracking
    contains_caffeine BOOLEAN DEFAULT FALSE,
    caffeine_mg FLOAT,
    
    -- Trigger tracking (for headaches/symptoms)
    trigger_foods VARCHAR[],
    is_trigger_suspected BOOLEAN DEFAULT FALSE,
    
    -- Estimation metadata
    nutrition_source VARCHAR DEFAULT 'estimated',  -- 'estimated', 'manual', 'scanned', 'api'
    estimation_confidence FLOAT,  -- 0-1
    llm_reasoning VARCHAR,
    
    notes VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- SYMPTOMS TABLE
-- Health symptoms with detailed tracking
-- =============================================
CREATE TABLE IF NOT EXISTS symptoms (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    
    -- Symptom identification
    symptom_type VARCHAR NOT NULL,
    symptom_subtype VARCHAR,  -- e.g., 'migraine', 'tension', 'cluster'
    custom_type VARCHAR,
    
    -- Severity and timing
    severity INTEGER NOT NULL,  -- 1-10
    onset_time TIME,
    end_time TIME,
    duration_minutes INTEGER,
    
    -- Location (for pain-based symptoms)
    body_location VARCHAR,
    custom_location VARCHAR,
    laterality VARCHAR,  -- 'left', 'right', 'bilateral', 'central'
    pain_character VARCHAR,  -- 'throbbing', 'stabbing', 'dull', 'burning'
    
    -- Associated symptoms
    with_nausea BOOLEAN DEFAULT FALSE,
    with_light_sensitivity BOOLEAN DEFAULT FALSE,
    with_sound_sensitivity BOOLEAN DEFAULT FALSE,
    with_aura BOOLEAN DEFAULT FALSE,
    with_visual_disturbance BOOLEAN DEFAULT FALSE,
    
    -- Triggers and treatment
    suspected_triggers VARCHAR[],
    treatment_taken VARCHAR,
    treatment_effective BOOLEAN,
    
    notes VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- WEATHER TABLE
-- Environmental conditions
-- =============================================
CREATE TABLE IF NOT EXISTS weather (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    recorded_at TIMESTAMP,
    
    -- Temperature
    temp_c FLOAT,
    temp_high_c FLOAT,
    temp_low_c FLOAT,
    feels_like_c FLOAT,
    
    -- Atmospheric
    pressure_hpa FLOAT,
    pressure_trend VARCHAR,  -- 'rising', 'falling', 'stable'
    pressure_change_3h FLOAT,
    humidity_percent INTEGER,
    
    -- Wind
    wind_speed_kmh FLOAT,
    wind_gust_kmh FLOAT,
    wind_direction_deg INTEGER,
    
    -- Precipitation
    precipitation_mm FLOAT,
    precipitation_probability INTEGER,
    
    -- Conditions
    description VARCHAR,
    cloud_cover_percent INTEGER,
    visibility_km FLOAT,
    uv_index FLOAT,
    
    -- Air quality
    aqi INTEGER,
    pm25 FLOAT,
    pm10 FLOAT,
    
    -- Astronomy (for seasonal affective analysis)
    sunrise TIME,
    sunset TIME,
    daylight_minutes INTEGER,
    moon_phase VARCHAR,
    
    -- Source
    source VARCHAR DEFAULT 'openweathermap',
    location_lat FLOAT,
    location_lon FLOAT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entry_date, source)
);

-- =============================================
-- VITALS TABLE
-- Manual health measurements
-- =============================================
CREATE TABLE IF NOT EXISTS vitals (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    recorded_at TIME,
    
    -- Weight
    weight_kg FLOAT,
    body_fat_percent FLOAT,
    muscle_mass_kg FLOAT,
    
    -- Blood pressure
    systolic_bp INTEGER,
    diastolic_bp INTEGER,
    
    -- Heart
    resting_heart_rate INTEGER,
    
    -- Blood glucose
    blood_glucose_mgdl FLOAT,
    glucose_timing VARCHAR,  -- 'fasting', 'post_meal', 'random'
    
    -- Temperature
    body_temperature_c FLOAT,
    
    -- Respiratory
    blood_oxygen_percent INTEGER,
    respiratory_rate INTEGER,
    
    notes VARCHAR,
    source VARCHAR DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- MEDICATIONS TABLE
-- Medication tracking
-- =============================================
CREATE TABLE IF NOT EXISTS medications (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    time_taken TIME,
    
    -- Medication info
    name VARCHAR NOT NULL,
    dosage VARCHAR,
    dosage_mg FLOAT,
    form VARCHAR,  -- 'tablet', 'capsule', 'liquid', 'injection'
    
    -- Purpose
    purpose VARCHAR,  -- 'pain', 'preventive', 'rescue'
    for_symptom_id VARCHAR,  -- links to symptoms table
    
    -- Effectiveness
    effectiveness INTEGER,  -- 1-10
    side_effects VARCHAR,
    
    -- Prescription info
    is_prescription BOOLEAN DEFAULT FALSE,
    prescribing_doctor VARCHAR,
    
    notes VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- SUPPLEMENTS TABLE
-- Supplement intake tracking
-- =============================================
CREATE TABLE IF NOT EXISTS supplements (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    time_taken TIME,
    
    name VARCHAR NOT NULL,
    brand VARCHAR,
    dosage VARCHAR,
    dosage_amount FLOAT,
    dosage_unit VARCHAR,  -- 'mg', 'mcg', 'IU', 'g'
    supplement_type VARCHAR,  -- 'vitamin', 'mineral', 'herb', 'amino_acid'
    
    notes VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- HYDRATION TABLE
-- Fluid intake tracking
-- =============================================
CREATE TABLE IF NOT EXISTS hydration (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    time_consumed TIME,
    
    beverage_type VARCHAR NOT NULL,  -- 'water', 'coffee', 'tea', 'juice'
    volume_ml FLOAT NOT NULL,
    
    -- Content
    contains_caffeine BOOLEAN DEFAULT FALSE,
    caffeine_mg FLOAT,
    contains_alcohol BOOLEAN DEFAULT FALSE,
    alcohol_units FLOAT,
    contains_sugar BOOLEAN DEFAULT FALSE,
    sugar_g FLOAT,
    
    -- Electrolytes
    sodium_mg FLOAT,
    potassium_mg FLOAT,
    
    notes VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- INCIDENTS TABLE
-- Notable health events
-- =============================================
CREATE TABLE IF NOT EXISTS incidents (
    id VARCHAR PRIMARY KEY,
    entry_date DATE NOT NULL,
    time_occurred TIME,
    
    incident_type VARCHAR NOT NULL,
    custom_type VARCHAR,
    severity INTEGER,  -- 1-10
    
    location VARCHAR,
    custom_location VARCHAR,
    
    description VARCHAR,
    duration_minutes INTEGER,
    suspected_cause VARCHAR,
    action_taken VARCHAR,
    medical_attention BOOLEAN DEFAULT FALSE,
    
    notes VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- DAILY SUMMARY TABLE
-- Aggregated daily metrics for quick analysis
-- =============================================
CREATE TABLE IF NOT EXISTS daily_summary (
    entry_date DATE PRIMARY KEY,
    
    -- Subjective wellbeing
    overall_wellbeing INTEGER,
    energy_level INTEGER,
    stress_level INTEGER,
    mood VARCHAR,
    mood_score INTEGER,
    
    -- Sleep summary
    sleep_score INTEGER,
    total_sleep_minutes INTEGER,
    sleep_efficiency INTEGER,
    hrv_average FLOAT,
    
    -- Activity summary
    activity_count INTEGER DEFAULT 0,
    total_activity_minutes FLOAT DEFAULT 0,
    total_distance_km FLOAT DEFAULT 0,
    total_elevation_m FLOAT DEFAULT 0,
    total_calories_burned FLOAT DEFAULT 0,
    
    -- Nutrition summary
    meal_count INTEGER DEFAULT 0,
    total_calories FLOAT DEFAULT 0,
    total_protein_g FLOAT DEFAULT 0,
    total_carbs_g FLOAT DEFAULT 0,
    total_fat_g FLOAT DEFAULT 0,
    total_fiber_g FLOAT DEFAULT 0,
    total_water_ml FLOAT DEFAULT 0,
    total_caffeine_mg FLOAT DEFAULT 0,
    total_alcohol_units FLOAT DEFAULT 0,
    
    -- Symptom summary
    symptom_count INTEGER DEFAULT 0,
    worst_symptom_severity INTEGER,
    has_headache BOOLEAN DEFAULT FALSE,
    has_neuralgiaform BOOLEAN DEFAULT FALSE,
    
    -- Incident summary
    incident_count INTEGER DEFAULT 0,
    
    -- Weather summary
    temp_avg_c FLOAT,
    pressure_hpa FLOAT,
    pressure_change FLOAT,
    humidity_percent INTEGER,
    
    -- Vitals summary
    weight_kg FLOAT,
    resting_hr INTEGER,
    
    -- Medication summary
    medication_count INTEGER DEFAULT 0,
    rescue_medication_used BOOLEAN DEFAULT FALSE,
    
    -- Supplement summary
    supplement_count INTEGER DEFAULT 0,
    
    -- Notes
    morning_notes VARCHAR,
    evening_notes VARCHAR,
    general_notes VARCHAR,
    
    -- Metadata
    is_complete BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- CORRELATION CACHE TABLE
-- Pre-computed correlations for faster analysis
-- =============================================
CREATE TABLE IF NOT EXISTS correlation_cache (
    id VARCHAR PRIMARY KEY,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    days_analyzed INTEGER,
    start_date DATE,
    end_date DATE,
    
    factor_a VARCHAR,
    factor_b VARCHAR,
    correlation FLOAT,
    p_value FLOAT,
    sample_size INTEGER,
    
    is_significant BOOLEAN
);

-- =============================================
-- INDEXES
-- =============================================
CREATE INDEX IF NOT EXISTS idx_sleep_date ON sleep(entry_date);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(entry_date);
CREATE INDEX IF NOT EXISTS idx_meals_date ON meals(entry_date);
CREATE INDEX IF NOT EXISTS idx_symptoms_date ON symptoms(entry_date);
CREATE INDEX IF NOT EXISTS idx_symptoms_type ON symptoms(symptom_type);
CREATE INDEX IF NOT EXISTS idx_weather_date ON weather(entry_date);
CREATE INDEX IF NOT EXISTS idx_vitals_date ON vitals(entry_date);
CREATE INDEX IF NOT EXISTS idx_medications_date ON medications(entry_date);
CREATE INDEX IF NOT EXISTS idx_hydration_date ON hydration(entry_date);

-- =============================================
-- EXAMPLE QUERIES
-- =============================================

-- Get sleep trends for last 14 days
-- SELECT entry_date, sleep_score, total_sleep_minutes, hrv_average 
-- FROM sleep ORDER BY entry_date DESC LIMIT 14;

-- Correlate pressure with headaches
-- SELECT w.entry_date, w.pressure_hpa, s.severity
-- FROM weather w
-- JOIN symptoms s ON w.entry_date = s.entry_date
-- WHERE s.symptom_type LIKE '%headache%';

-- Daily nutrition totals
-- SELECT entry_date, SUM(calories) as total_cal, SUM(protein_g) as protein
-- FROM meals
-- GROUP BY entry_date
-- ORDER BY entry_date DESC;

-- Symptoms frequency by type
-- SELECT symptom_type, COUNT(*) as occurrences, AVG(severity) as avg_severity
-- FROM symptoms
-- GROUP BY symptom_type
-- ORDER BY occurrences DESC;
