\# Dataset Catalog



\## 1. Purpose



This document records the actual datasets, APIs and data sources identified for the AI-Based Smart Logistics \& Accessibility Intelligence Platform.



Each source is evaluated based on its availability, geographic coverage, data fields, format, licensing, reliability and suitability for the project.



\---



\# 2. Dataset Summary



| ID | Data Category | Dataset / API | Provider | Coverage | Format | ML Usage | Status |

|---|---|---|---|---|---|---|---|

| D01 | Road Network | To be verified | To be verified | NER | To be verified | Supporting | Pending |

| D02 | Bridge | To be verified | To be verified | NER | To be verified | Feature | Pending |

| D03 | Weather | To be verified | To be verified | NER | API | Feature | Pending |

| D04 | Historical Disruption | To be verified | To be verified | NER | To be verified | Target/Feature | Critical |

| D05 | Traffic | To be verified | To be verified | NER | API/Dataset | Feature | Pending |

| D06 | Geographic/Route | To be verified | To be verified | NER | Geospatial | Feature | Pending |

| D07 | Field Incidents | Platform | Our System | NER | Database | Feature | Planned |

| D08 | Vehicle GPS | Simulator | Our System | NER | JSON/API | Tracking | Planned |



\---



\# 3. Road Network Dataset



\## Dataset Name

To be verified



\## Provider

To be verified



\## Official Source

To be added after verification.



\## Geographic Coverage

North Eastern Region of India



\## Data Type

Geospatial road-network data.



\## Expected Information

\- Road geometry

\- Road type

\- Road name

\- Connectivity

\- Speed information where available

\- Road attributes



\## Format

To be verified.



\## Update Frequency

To be verified.



\## License

To be verified.



\## Cost

To be verified.



\## Project Usage

\- GIS visualization

\- Route calculation

\- Route distance calculation

\- Alternative route generation

\- Connectivity analysis



\## ML Usage

Supporting feature/data source.



\## Status

Pending verification.



\---



\# 4. Bridge \& Infrastructure Dataset



\## Dataset Name

To be verified



\## Provider

To be verified



\## Official Source

To be added after verification.



\## Geographic Coverage

North Eastern Region of India



\## Required Information

\- Bridge location

\- Bridge identifier

\- Bridge status

\- Bridge condition where available

\- Associated road

\- Infrastructure incidents



\## Format

To be verified.



\## Update Frequency

To be verified.



\## License

To be verified.



\## Cost

To be verified.



\## Project Usage

\- Infrastructure monitoring

\- Accessibility analysis

\- Risk assessment

\- GIS visualization



\## ML Usage

Potential ML features.



\## Status

Pending verification.



\---



\# 5. Weather Dataset / API



\## Dataset / API Name

To be verified



\## Provider

To be verified



\## Official Source

To be added after verification.



\## Geographic Coverage

North Eastern Region of India



\## Required Information

\- Rainfall

\- Temperature

\- Humidity

\- Wind speed

\- Weather condition

\- Forecast

\- Severe weather indicators where available



\## Format

API / JSON or other verified format.



\## Update Frequency

To be verified.



\## License / API Terms

To be verified.



\## Cost

Free tier / paid status to be verified.



\## Project Usage

\- Weather monitoring

\- Disruption risk prediction

\- Route risk analysis

\- Automated alerts



\## ML Usage

Major ML input features.



\## Status

Pending verification.



\---



\# 6. Historical Disruption Dataset



\## Dataset Name

To be verified



\## Provider

To be verified



\## Official Source

To be added after verification.



\## Geographic Coverage

North Eastern Region of India



\## Required Information

\- Incident date

\- Location

\- Disruption type

\- Road/bridge affected

\- Severity

\- Duration

\- Weather conditions

\- Route affected

\- Restoration status



\## Format

To be verified.



\## Time Coverage

To be verified.



\## License

To be verified.



\## Cost

To be verified.



\## Project Usage

Historical analysis and ML training.



\## ML Usage

CRITICAL.



This dataset will help establish the relationship between transportation conditions and actual disruption events.



The final target-labeling strategy will be determined only after examining the verified data.



\## Status

Critical — pending verification.



\---



\# 7. Traffic Dataset / API



\## Dataset / API Name

To be verified



\## Provider

To be verified



\## Geographic Coverage

North Eastern Region



\## Required Information

\- Traffic level

\- Congestion

\- Vehicle density where available

\- Average speed where available

\- Traffic incidents



\## Format

To be verified.



\## Update Frequency

To be verified.



\## Cost

To be verified.



\## Project Usage

\- Congestion analysis

\- Travel-time estimation

\- Route risk assessment

\- Alternative route recommendation



\## ML Usage

Potential ML features.



\## Status

Pending verification.



\---



\# 8. Geographic \& Route Data



\## Dataset / Service

To be verified



\## Provider

To be verified



\## Required Information

\- Latitude

\- Longitude

\- Road geometry

\- Route distance

\- Route duration

\- Origin

\- Destination

\- Terrain/elevation where available



\## Format

Geospatial / API.



\## Project Usage

\- GIS dashboard

\- Route calculation

\- Alternative route generation

\- Geographic risk visualization



\## ML Usage

Route-related features.



\## Status

Pending verification.



\---



\# 9. Field Incident Data



\## Source

Platform-generated data.



\## Data Collection Method

Authorized users submit incidents through the platform.



\## Required Information

\- Incident ID

\- Incident type

\- Description

\- Latitude

\- Longitude

\- Severity

\- Timestamp

\- Photo/evidence

\- Road/bridge affected

\- Report status



\## Format

Database records / JSON.



\## Project Usage

\- Real-time incident reporting

\- Infrastructure monitoring

\- Risk updates

\- Alert generation



\## ML Usage

Potential real-time and future training features.



\## Status

Planned.



\---



\# 10. Vehicle / GPS Data



\## Source

GPS simulator for V1.



\## Required Information

\- Vehicle ID

\- Latitude

\- Longitude

\- Timestamp

\- Speed

\- Heading

\- Current route

\- Delivery status



\## Format

JSON / API / database.



\## Project Usage

\- Vehicle tracking

\- Delivery monitoring

\- Route monitoring

\- Estimated arrival information



\## ML Usage

Potential future feature.



\## Status

Simulated for V1.



\---



\# 11. Data Reliability Classification



| Classification | Meaning |

|---|---|

| Verified | Source has been checked and confirmed suitable |

| Pending Verification | Source/data availability still needs to be checked |

| User Generated | Data collected through our platform |

| Simulated | Generated for development/demo purposes |

| Future Integration | Planned for later versions |



\---



\# 12. Dataset Selection Criteria



Every dataset will be evaluated based on:



\- Relevance to the NER region

\- Data quality

\- Geographic coverage

\- Temporal coverage

\- Required features

\- Reliability

\- Update frequency

\- Availability

\- Licensing

\- Cost

\- ML suitability



\---



\# 13. Data Integration



The selected datasets will be integrated using common attributes such as:



\- Latitude

\- Longitude

\- Timestamp

\- Road identifier

\- Bridge identifier

\- Incident identifier

\- Route identifier



The integrated data will form the foundation for the ML and GIS components.



\---



\# 14. Data Pipeline



Verified Data Sources

&#x20;       ↓

Data Collection

&#x20;       ↓

Data Validation

&#x20;       ↓

Data Cleaning

&#x20;       ↓

Data Integration

&#x20;       ↓

Feature Engineering

&#x20;       ↓

Unified Dataset

&#x20;       ↓

ML Training / Prediction



\---



\# 15. Dataset Status



\## Verified

\- To be updated after research.



\## Pending Verification

\- Road Network

\- Bridge / Infrastructure

\- Weather

\- Historical Disruptions

\- Traffic

\- Geographic / Route



\## Planned

\- Field Incident Data



\## Simulated

\- Vehicle / GPS Data



\---



\# 16. Final Selected Datasets



This section will be updated after dataset research.



| Dataset | Selected? | Reason |

|---|---|---|

| Road Network | Pending | |

| Bridge / Infrastructure | Pending | |

| Weather | Pending | |

| Historical Disruption | Pending | |

| Traffic | Pending | |

| Geographic / Route | Pending | |

| Field Incidents | Planned | |

| Vehicle GPS | Simulated V1 | |

