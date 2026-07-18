WITH null_sections AS (
    SELECT
        case_id,
        COUNT(*) AS null_section_count
    FROM parsed_sections
    WHERE document_id IS NULL
    GROUP BY case_id
),
document_counts AS (
    SELECT
        ns.case_id,
        ns.null_section_count,
        COUNT(ud.id) FILTER (
            WHERE ud.document_type = 'requirement'
        ) AS req_doc_count,
        MAX(ud.id) FILTER (
            WHERE ud.document_type = 'requirement'
        ) AS latest_req_doc_id
    FROM null_sections ns
    LEFT JOIN uploaded_documents ud ON ns.case_id = ud.case_id
    GROUP BY ns.case_id, ns.null_section_count
)
SELECT
    case_id,
    null_section_count,
    req_doc_count,
    latest_req_doc_id
FROM document_counts
ORDER BY case_id;
