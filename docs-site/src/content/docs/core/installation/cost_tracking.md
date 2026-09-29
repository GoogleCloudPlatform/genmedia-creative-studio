---
title: "Cost Tracking Analytics"
---

Tracking API usage and correlating it to cost-per-user is a standard requirement for transitioning the GenMedia Creative Studio to a production environment. 

The application implements structured JSON logging via the `genmedia.analytics` logger. By streaming these logs to Google Cloud BigQuery, administrators can easily track usage, monitor API calls, and calculate costs.

## 1. Setting up a Log Router Sink

Google Cloud allows you to automatically route specific logs from Cloud Run directly into a BigQuery dataset for analysis.

1. Navigate to **Logging > Log Router** in the Google Cloud Console.
2. Click **Create Sink**.
3. **Sink Details:** Name it `genmedia-analytics-sink`.
4. **Sink Destination:** Choose **BigQuery dataset**. Select or create a new dataset (e.g., `genmedia_analytics`).
5. **Inclusion Filter:** This is the most critical step. You only want to route the analytics logs, not standard application traffic. Use the following filter:
   ```text
   jsonPayload.name = "genmedia.analytics"
   jsonPayload.event_type = "model_call"
   ```
6. **Create Sink:** Google Cloud will automatically create the required table schema in BigQuery as new logs arrive.

## 2. Understanding the Log Payload

The application enriches every `model_call` event with the following metadata inside the `jsonPayload.extra_data` field:

*   `model_name`: The specific model version used (e.g., `gemini-3.8-flash`, `veo-3.1-lite-generate-001`).
*   `status`: Either `success` or `failure`.
*   `duration_ms`: The total execution time of the API call.
*   `user_email`: The email of the user who initiated the request.
*   `session_id`: The unique session identifier.
*   `details`: A JSON object containing model-specific parameters (e.g., `aspect_ratio`, `num_images_generated`, `video_duration`).

## 3. Correlating Usage with Cost in BigQuery

Once the logs are flowing into BigQuery, you can use SQL to aggregate usage and multiply it by the standard Google Cloud pricing.

Here is an example SQL query to calculate the cost of Veo Video Generation per user for the current month:

```sql
WITH VeoUsage AS (
  SELECT
    JSON_EXTRACT_SCALAR(jsonPayload.extra_data, "$.user_email") AS user_email,
    JSON_EXTRACT_SCALAR(jsonPayload.extra_data, "$.model_name") AS model_name,
    CAST(JSON_EXTRACT_SCALAR(JSON_EXTRACT(jsonPayload.extra_data, "$.details"), "$.duration_seconds") AS INT64) AS duration_seconds,
    timestamp
  FROM
    `your-project.genmedia_analytics.run_googleapis_com_stdout`
  WHERE
    JSON_EXTRACT_SCALAR(jsonPayload.extra_data, "$.event_type") = "model_call"
    AND JSON_EXTRACT_SCALAR(jsonPayload.extra_data, "$.status") = "success"
    AND JSON_EXTRACT_SCALAR(jsonPayload.extra_data, "$.model_name") LIKE "veo-%"
    AND EXTRACT(MONTHFROM timestamp) = EXTRACT(MONTH FROM CURRENT_TIMESTAMP())
)

SELECT
  user_email,
  model_name,
  SUM(duration_seconds) AS total_seconds_generated,
  -- Example: Assuming Veo costs $0.20 per second of generated video
  SUM(duration_seconds) * 0.20 AS estimated_cost_usd
FROM
  VeoUsage
GROUP BY
  user_email, model_name
ORDER BY
  estimated_cost_usd DESC;
```

> **Note:** Pricing changes over time. Always refer to the official [Google Cloud AI Pricing Page](https://cloud.google.com/vertex-ai/pricing) to update your correlation multipliers.

## 4. A Note on Historical Logs

Creating a Log Router Sink only routes *future* logs. It will not automatically backfill your BigQuery dataset with historical logs generated prior to the sink's creation.

If you need to analyze historical costs for an existing instance:
1. **One-Time Export:** Navigate to **Logging > Logs Exporer**, filter for your analytics logs (`jsonPayload.name="genmedia.analytics"`), and use the **Actions > Download/Export** feature to manually copy the last 30 days of logs into your BigQuery table.
2. **Log Analytics:** Alternatively, if your Cloud Logging bucket is upgraded to support **Log Analytics**, you can query your historical logs directly using standard SQL without needing a Log Router Sink at all.
