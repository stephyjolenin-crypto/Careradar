# CareRadar Plan

## Emergency types
cardiac, stroke, accident, pregnancy

## Hospital information we store
name, location (lat, lng), phone, specialties,
ICU beds free, general beds free, ventilators free,
oxygen available (yes/no), blood groups, last updated time

## What the backend can do
/health  - check the server is running
/rank    - give a location and emergency type, get hospitals in best order
/triage  - give symptoms text, get emergency type back
/alert   - tell a hospital a patient is coming
