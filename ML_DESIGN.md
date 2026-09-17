\# AI/ML Design



\## 1. AI/ML Objective



The AI system will predict the disruption and accessibility risk of transportation routes in the North Eastern Region (NER).



The model will analyze weather, infrastructure, traffic, incident and route-related information to estimate the likelihood that a route may become disrupted or difficult to access.



The prediction will support route selection, alternative route recommendation and automated alerts.



\---



\## 2. AI/ML Problem



\### Primary Problem



Predict transportation route disruption risk based on current and historical conditions.



\### ML Task



Initial approach:

\- Supervised Machine Learning

\- Classification



The system will classify routes into:



\- Low Risk

\- Medium Risk

\- High Risk



The final classification thresholds and labels will be determined based on the available historical disruption data.



\---



\## 3. Input Features



The model will use the following features.



\### Weather Features

\- Rainfall

\- Temperature

\- Humidity

\- Wind Speed

\- Weather Condition

\- Forecast Information



\### Infrastructure Features

\- Road Condition

\- Bridge Condition

\- Road Status

\- Bridge Status

\- Road Type



\### Transportation Features

\- Traffic Level

\- Recent Incidents

\- Historical Incidents

\- Route Distance



\### Geographic Features

\- Route Characteristics

\- Elevation / Terrain Information where available

\- Geographic Location



\---



\## 4. Target Variable



The primary target will represent whether a route is at risk of disruption.



Initial output:



\- Low Risk

\- Medium Risk

\- High Risk



The model should also provide a numerical disruption probability/risk score.



Example:



Risk Score: 82%



Risk Level: HIGH



The final target-labeling strategy will be defined after examining the available historical disruption dataset.



\---



\## 5. ML Models



The following models will be evaluated:



\### Baseline Model

\- Logistic Regression



\### Main Candidate

\- Random Forest Classifier



Additional models may be evaluated later depending on dataset size and performance.



The final model will be selected based on validation performance rather than assuming one model is better beforehand.



\---



\## 6. Data Processing



Before training, the data will go through:



1\. Data collection

2\. Data cleaning

3\. Missing-value handling

4\. Duplicate removal

5\. Categorical data encoding

6\. Feature scaling where required

7\. Feature engineering

8\. Train/validation/test split



The preprocessing pipeline must be applied consistently to both training and prediction data.



\---



\## 7. Model Training



The cleaned and processed dataset will be used to train the selected ML models.



The models will be compared using the defined evaluation metrics.



The best-performing suitable model will be saved and integrated into the backend prediction service.



\---



\## 8. Model Evaluation



The following metrics will be used:



\- Accuracy

\- Precision

\- Recall

\- F1-Score

\- Confusion Matrix



Special attention will be given to recall for High-Risk routes because failing to identify a potentially dangerous/disrupted route is more serious than generating an additional warning.



\---



\## 9. Prediction Output



For each route, the ML system will return:



\- Risk Score

\- Risk Level

\- Prediction Timestamp

\- Major contributing factors



Example:



Route: Guwahati → Shillong



Risk Score: 78%



Risk Level: HIGH



Major Factors:

\- Heavy rainfall

\- Recent road incident

\- Poor road condition



\---



\## 10. ML Decision Flow



Weather Data

\+

Infrastructure Data

\+

Traffic Data

\+

Incident Data

\+

Historical Data

\+

Route Data



↓



Data Preprocessing



↓



Feature Engineering



↓



ML Model



↓



Risk Prediction



↓



Risk Score + Risk Level



↓



Route Analysis



↓



Alternative Route Recommendation



↓



Alert / Decision Support



\---



\## 11. Explainability



The system should provide understandable reasons behind a prediction.



For example:



"High disruption risk is predicted because of heavy rainfall, poor road condition and recent incidents along the route."



This will make the system more useful for logistics operators and decision-makers.



\---



\## 12. Future AI/ML Enhancements



The system can later be extended with:



\- Time-series disruption forecasting

\- Anomaly detection

\- Computer Vision for road and bridge damage

\- Satellite imagery analysis

\- Advanced weather prediction

\- Geospatial risk modelling

\- Explainable AI

\- Continuous model retraining

\- Real-time learning from field reports

