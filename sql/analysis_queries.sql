-- ---------------------------------------------------------------------------
-- Classroom AV Ticket Analysis — SQL companion queries
--
-- These mirror the pandas analysis in notebooks/av_ticket_analysis.ipynb,
-- written as they would run against a reporting warehouse holding the
-- ServiceNow export (av_tickets) and the AV asset inventory (classrooms).
--
-- Dialect: standard SQL. Queries 1–5 run unmodified on SQLite / Postgres /
-- BigQuery. Query 6 uses PERCENTILE_CONT (Postgres / BigQuery); the SQLite
-- equivalent is noted inline. Data is synthetic — see README.
--
-- Every query excludes the 25Live scheduling-integration rows (~70% of the
-- raw export): they are calendar syncs, not support demand. The notebook
-- additionally removes a small number of double-submitted duplicates, so
-- its counts sit slightly below these.
-- ---------------------------------------------------------------------------


-- 1. Monthly ticket volume (seasonality: spring peaks, summer/December troughs)
SELECT
    strftime('%Y-%m', created_at) AS month,   -- Postgres/BQ: DATE_TRUNC('month', created_at)
    COUNT(*)                      AS tickets
FROM av_tickets
WHERE created_by <> '25Live'
GROUP BY 1
ORDER BY 1;


-- 2. Ticket volume by classroom, with AV configuration from the asset table
--    (TRIM guards against whitespace-padded room IDs; blank rooms — ~30% of
--    tickets — are excluded from room-level analysis by the join)
SELECT
    TRIM(t.classroom_id)  AS classroom_id,
    c.config_variant,
    COUNT(*)              AS tickets
FROM av_tickets t
JOIN classrooms c
    ON TRIM(t.classroom_id) = c.classroom_id
WHERE t.created_by <> '25Live'
GROUP BY 1, 2
ORDER BY tickets DESC;


-- 3. Tickets per room by configuration variant
--    (the disproportionate-volume finding)
SELECT
    c.config_variant,
    COUNT(*)                                        AS tickets,
    COUNT(DISTINCT c.classroom_id)                  AS rooms,
    ROUND(COUNT(*) * 1.0
          / COUNT(DISTINCT c.classroom_id), 1)      AS tickets_per_room
FROM av_tickets t
JOIN classrooms c
    ON TRIM(t.classroom_id) = c.classroom_id
WHERE t.created_by <> '25Live'
GROUP BY 1
ORDER BY tickets_per_room DESC;


-- 4. Display-signal issue share: legacy-matrix rooms vs everything else
--    (the configuration-pattern finding)
SELECT
    CASE WHEN c.config_variant = 'legacy_matrix_v1'
         THEN 'legacy_matrix_rooms' ELSE 'other_rooms' END AS room_group,
    COUNT(*) AS tickets,
    SUM(CASE WHEN t.subcategory IN
             ('No display / HDMI handshake', 'Input switching failure')
             THEN 1 ELSE 0 END) AS display_signal_tickets,
    ROUND(100.0 * SUM(CASE WHEN t.subcategory IN
             ('No display / HDMI handshake', 'Input switching failure')
             THEN 1 ELSE 0 END) / COUNT(*), 1) AS display_signal_pct
FROM av_tickets t
JOIN classrooms c
    ON TRIM(t.classroom_id) = c.classroom_id
WHERE t.created_by <> '25Live'
GROUP BY 1;


-- 5. Repeat tickets: same room + same subcategory within 14 days
--    (LAG over a room/issue partition; the expensive-ticket metric)
WITH ordered AS (
    SELECT
        t.ticket_id,
        TRIM(t.classroom_id) AS classroom_id,
        t.subcategory,
        c.config_variant,
        t.created_at,
        LAG(t.created_at) OVER (
            PARTITION BY TRIM(t.classroom_id), t.subcategory
            ORDER BY t.created_at
        ) AS prev_created_at
    FROM av_tickets t
    JOIN classrooms c
        ON TRIM(t.classroom_id) = c.classroom_id
    WHERE t.created_by <> '25Live'
)
SELECT
    config_variant,
    COUNT(*) AS tickets,
    SUM(CASE WHEN julianday(created_at) - julianday(prev_created_at) <= 14
             THEN 1 ELSE 0 END) AS repeats,      -- Postgres: created_at - prev_created_at <= INTERVAL '14 days'
    ROUND(100.0 * SUM(CASE WHEN julianday(created_at) - julianday(prev_created_at) <= 14
             THEN 1 ELSE 0 END) / COUNT(*), 1) AS repeat_pct
FROM ordered
GROUP BY 1
ORDER BY repeat_pct DESC;


-- 6. Median resolution time by category, in hours (resolved tickets only;
--    calendar time — queue time included, hence medians in hours-to-days)
--    Postgres / BigQuery syntax; SQLite lacks PERCENTILE_CONT — the SQLite
--    workaround is an ordered LIMIT/OFFSET subquery per group.
SELECT
    category,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
          (ORDER BY resolution_time_minutes) / 60.0, 1) AS median_resolution_hours,
    COUNT(*) AS resolved_tickets
FROM av_tickets
WHERE created_by <> '25Live'
  AND resolved_at IS NOT NULL
GROUP BY category
ORDER BY median_resolution_hours;
