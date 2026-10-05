# Independent labels

Create `labels/{labeler_id}/{doc_id}.json` from the matching packet.

One reviewer, one file. A second reviewer creates another directory. Neither
file is an adjudication. Copy the packet's `gold_document` fields that you
filled, plus `cases`. Do not include `source_text` or model predictions.

`split` stays `dev`. The validator reads the packet's seated split and rejects
any other document.
