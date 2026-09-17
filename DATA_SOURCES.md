\# SIH26002 — Data Sources \& Data Requirements



\## 1. Purpose



This document defines the data required by the AI-Based Smart Logistics \& Accessibility Intelligence Platform, the planned sources of the data, and how each data type will be used by the system.



\---



\## 2. Road Network Data



\### Required Data

\- Road name / road ID

\- Geographic coordinates

\- Road type

\- Road connectivity

\- Road status

\- Route geometry



\### Planned Source

OpenStreetMap (OSM)



\### Cost

Free and open data.



\### Usage

Used for GIS visualization, route calculation, connectivity analysis and alternative-route recommendation.



\---



\## 3. Bridge Data



\### Required Data

\- Bridge name / bridge ID

\- Geographic coordinates

\- Bridge location

\- Bridge status

\- Bridge condition

\- Reported damage

\- Risk information



\### Planned Source

Available open/official infrastructure data and field reports.



\### Cost

Depends on the specific official/open dataset used.



\### Usage

Used to monitor bridge accessibility and contribute to route-risk prediction.



\### Important Note

The system will not assume that live bridge-condition information is automatically available. Actual condition updates will come from verified data sources, field reports and later sensor-based integrations.



\---



\## 4. Weather Data



\### Required Data

\- Rainfall

\- Temperature

\- Humidity

\- Wind speed

\- Weather condition

\- Weather forecast



\### Planned Source

Weather API.



\### Cost

Use a free-tier/free weather data source for V1.



\### Usage

Weather information will be used for current-condition monitoring and as an input to the AI/ML risk prediction system.



\---



\## 5. Vehicle / GPS Data



\### Required Data

\- Vehicle ID

\- Vehicle number

\- Current latitude

\- Current longitude

\- Speed

\- Destination

\- Vehicle status

\- Estimated arrival time



\### Planned Source

GPS simulation for V1.



\### Future Source

Real GPS/IoT telemetry.



\### Cost

Simulation is free.



\### Usage

Used to visualize vehicle movement, monitor deliveries and identify vehicles approaching high-risk routes.



\---



\## 6. Incident / Field Report Data



\### Required Data

\- Incident ID

\- Incident type

\- Description

\- Location

\- Latitude

\- Longitude

\- Severity

\- Date and time

\- Photo / media

\- Reporter information



\### Planned Source

Field reporting module developed as part of the platform.



\### Cost

Free for V1.



\### Usage

Field reports will provide real-time information about road blocks, bridge problems, landslides, floods and other transportation disruptions.



\---



\## 7. Historical Disruption Data



\### Required Data

\- Previous incidents

\- Road closures

\- Bridge disruptions

\- Flood/landslide events

\- Weather conditions during incidents

\- Location

\- Date and time

\- Duration of disruption

\- Severity



\### Planned Source

Public/open datasets and verified historical records.



\### Cost

Prefer free/open datasets.



\### Usage

Used for machine-learning model training and historical risk analysis.



\---



\## 8. Geographic / Route Data



\### Required Data

\- Road network

\- Locations

\- Route geometry

\- Distance

\- Connectivity

\- Possible alternative routes



\### Planned Source

OpenStreetMap-based geographic data and routing services.



\### Cost

Use free/open options for V1 where possible.



\### Usage

Used by the GIS dashboard and route intelligence module to calculate and visualize routes.



\---



\## 9. Data Classification



| Data Type | V1 Data Source | Status |

|---|---|---|

| Road Network | OpenStreetMap | Real/Open |

| Bridge Information | Open/Official Data + Field Reports | To be verified |

| Weather | Weather API | Real |

| Vehicle GPS | Simulator | Simulated |

| Incidents | Field Reporting Module | User/Field Generated |

| Historical Disruptions | Public/Open Datasets | To be identified |

| Geographic Data | OpenStreetMap | Real/Open |

| Route Data | Routing Service | Real/Generated |



\---



\## 10. Data Flow



Data will enter the platform through multiple sources:



Weather API

&#x20;       ↓

Infrastructure Data

&#x20;       ↓

GPS / Vehicle Data

&#x20;       ↓

Field Reports

&#x20;       ↓

Historical Data

&#x20;       ↓

Data Processing Layer

&#x20;       ↓

Database

&#x20;       ↓

AI/ML Risk Engine

&#x20;       ↓

GIS \& Decision Support



\---



\## 11. Data Used by the AI/ML Model



The initial prediction model will consider factors such as:



\- Rainfall

\- Weather conditions

\- Road condition

\- Bridge condition

\- Traffic level

\- Historical incidents

\- Previous disruptions

\- Route characteristics



\### Expected Output



The model will generate:



\- Risk Score

\- Risk Level

\- Predicted Accessibility / Disruption Status



Example:



Risk Score: 82%

Risk Level: HIGH

Predicted Status: High Disruption Probability



\---



\## 12. Data Reliability



The system will distinguish between:



\- Verified/official data

\- Open/public data

\- Field-reported data

\- Simulated data



Simulated data will be used only where real-time data is unavailable during V1 development and testing. It will not be presented as real-world live data.



\---



\## 13. Future Data Integration



The platform can later be extended with:



\- Real GPS devices

\- IoT bridge/road sensors

\- Computer vision from field images

\- Satellite/geospatial data

\- Government infrastructure databases

\- Real-time traffic data

\- Advanced weather forecasting data



\---



\## 14. Data Source Principle



The project will prioritize free, open and publicly available data sources wherever possible. Paid APIs or services will not be required for the initial V1 unless a specific capability cannot reasonably be achieved using free/open alternatives.

