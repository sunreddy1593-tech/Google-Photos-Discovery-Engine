# Revision 03: annotations and evidence

Read APPROVAL.md for scoped approvals and the core-scope exception. All case fields and quotes are preserved from revision 02.

## google_support-2a080da4b930

> I'm trying to search for one of my family in a Google photos album. It is not a shared album. It seems you can't search for a face within a specific album, which means I have to scroll through hundreds of photos to find the one I want. Any tips?

Scope: `core_incomplete_recall`; reason: `known_item_retrieval_journey_described`; cases: 1

AI-assisted unapproved draft. Not an independent human label. The user wants a particular family photo inside an album and describes unavailable face search. No forgotten or approximate cue is stated. Sunayana directed core scope on 2026-10-04. This is a documented scope-criteria exception: the body does not demonstrate incomplete recall under spec Section 9.1. Existing known-item journey reason, case values and evidence are retained; forgotten information and trigger are not invented to justify the label. No classification rule or prompt changed.

- `known_item_status`: `stated`; `"explicit"`
- `target_asset_type`: `stated`; `"photo"`
- `outcome`: `not_stated`; `null`
- `severity`: `not_stated`; `null`
- `reformulation_count`: `not_stated`; `null`
- `target_subjects`: `stated`; `[{"value": "person", "detail": "one of my family"}]`
- `remembered_cues`: `stated`; `[{"value": "relationship", "detail": null}]`
- `forgotten_information`: `not_stated`; `[]`
- `query_strategies`: `stated`; `[{"value": "person_or_face_search", "detail": null}]`
- `system_responses`: `uncertain`; `[{"value": "filter_or_scope_mismatch", "detail": null}]`
- `workarounds`: `not_stated`; `[]`
- `impact_signals`: `not_stated`; `[]`
- `retrieval_trigger`: `not_stated`; `null`
- `exact_query`: `not_stated`; `null`
- `query_paraphrase`: `not_stated`; `null`

Evidence:

- `known_item_status` [212, 234): to find the one I want
- `target_asset_type` [178, 234): scroll through hundreds of photos to find the one I want
- `target_subjects` [25, 41): one of my family
- `remembered_cues` [25, 41): one of my family
- `query_strategies` [94, 154): It seems you can't search for a face within a specific album
- `system_responses` [94, 154): It seems you can't search for a face within a specific album

Face search is the requested approach, not a reported exact query. 'Have to scroll' describes the required alternative; completed scrolling, time consumed and final outcome are not established. The trigger is not stated. The scope limitation is hedged ('It seems'), so the reported system behavior is uncertain.

## google_support-4f34e2312ca6

> I went to Google Photos to look back at old photos and videos, but suddenly they all disappeared. I'm absolutely sure I didn't delete them, and no one has accessed my account. However, one thing that puzzles me is that I recently bought a tablet and connected it to the account where the photos and videos disappeared. It seems like it was linked to Google Photos. So I disconnected the tablet because I wanted to back up photos only to my phone. After that, when I checked my account again, all the old photos and videos from several years ago were gone

Scope: `out_of_scope`; reason: `storage_backup_or_sync`; cases: 0

AI-assisted unapproved draft. Not an independent human label. Bulk photos/videos disappear after connecting and disconnecting a tablet/account. This is a data availability/backup story, with no particular remembered item or retrieval journey. Deletion is not confirmed.

## google_support-5b2ec98df32b

> My photo memories come up and I can see randomly but how do I go back to view them?

Scope: `adjacent_known_item_retrieval`; reason: `known_item_retrieval_journey_described`; cases: 1

AI-assisted revision. Sunayana approved adjacent scope on 2026-10-04 after reviewing the draft. Revisiting already displayed photo Memories is treated as a known-target collection retrieval need. No incomplete recall is stated. The inclusion reason and new single-case details remain AI proposals pending confirmation. This is not an independent human label or adjudication.

- `known_item_status`: `stated`; `"explicit"`
- `target_asset_type`: `stated`; `"photo"`
- `outcome`: `not_stated`; `null`
- `severity`: `not_stated`; `null`
- `reformulation_count`: `not_stated`; `null`
- `target_subjects`: `not_stated`; `[]`
- `remembered_cues`: `not_stated`; `[]`
- `forgotten_information`: `not_stated`; `[]`
- `query_strategies`: `not_stated`; `[]`
- `system_responses`: `not_stated`; `[]`
- `workarounds`: `not_stated`; `[]`
- `impact_signals`: `not_stated`; `[]`
- `retrieval_trigger`: `not_stated`; `null`
- `exact_query`: `not_stated`; `null`
- `query_paraphrase`: `not_stated`; `null`

Evidence:

- `known_item_status` [0, 48): My photo memories come up and I can see randomly
- `target_asset_type` [0, 17): My photo memories

New AI-assisted case draft following Sunayana's approved adjacent scope. The known target is the previously displayed photo Memories collection, not an identified individual photo. The source asks how to revisit it. It states no incomplete recall, executed query, returned failure, workaround, final outcome, impact, severity or motive. These case-field judgments and expected_case_count=1 have not received blanket human approval. Independent second human review remains required.

## google_support-8c6ab430fbee

> I backed up new photos for my google account and when they finished backing up i opened the google photos app and 90% of my old photos were not there and I can't find them in the trash section or anywhere in the google account
> 
> I tried many thing and still can't find them, i need help because these photos are so important to me and they disappeared suddenly.

Scope: `out_of_scope`; reason: `storage_backup_or_sync`; cases: 0

AI-assisted unapproved draft. Not an independent human label. The source describes 90% of old photos disappearing after backup, including absence from trash/account. This is bulk backup/data availability, rather than retrieval of a particular remembered item. The source does not establish actual deletion.

## play_store-fb8c41525287

> suddenly there are issues with photos disappearing after editing. if you manage to find them and reopen them, edit/share/ask buttons on the bottom no longer function.

Scope: `out_of_scope`; reason: `editing_sharing_or_printing`; cases: 0

AI-assisted unapproved draft. Not an independent human label. Generic disappearing-after-editing and nonfunctional edit/share/ask controls, without a particular known target or a personal retrieval episode. The word 'find' does not establish a retrieval case.

## reddit-0d477b54fb9b

> I have a recent photo that has something very distinct in it. I am Trying to find an older photo I have of that same item but I have so many photos I can't find it and I don't remember when I took the photo. I was wondering if I could search Google photos on my phone to try to find a match to the current photo. Hope that makes sense. Thanks in advance!

Scope: `core_incomplete_recall`; reason: `known_item_with_incomplete_recall`; cases: 1

AI-assisted unapproved draft. Not an independent human label. The user explicitly has an older photo of the same item but cannot find it and cannot remember when it was taken. Their proposed reference-photo search is not reported as performed.

- `known_item_status`: `stated`; `"explicit"`
- `target_asset_type`: `stated`; `"photo"`
- `outcome`: `stated`; `"not_found"`
- `severity`: `not_stated`; `null`
- `reformulation_count`: `not_stated`; `null`
- `target_subjects`: `not_stated`; `[]`
- `remembered_cues`: `stated`; `[{"value": "object_or_subject", "detail": null}]`
- `forgotten_information`: `stated`; `[{"value": "exact_date", "detail": null}]`
- `query_strategies`: `not_stated`; `[]`
- `system_responses`: `not_stated`; `[]`
- `workarounds`: `not_stated`; `[]`
- `impact_signals`: `not_stated`; `[]`
- `retrieval_trigger`: `not_stated`; `null`
- `exact_query`: `not_stated`; `null`
- `query_paraphrase`: `not_stated`; `null`

Evidence:

- `known_item_status` [82, 121): an older photo I have of that same item
- `target_asset_type` [82, 121): an older photo I have of that same item
- `remembered_cues` [82, 121): an older photo I have of that same item
- `forgotten_information` [168, 206): I don't remember when I took the photo
- `outcome` [126, 163): I have so many photos I can't find it

The source states a failed search for the item, but not a specific system response or executed image-search strategy. 'When' is coded as exact_date; it does not establish forgotten time-of-day. The item is unspecified, so no subject type is inferred. No stated impact, severity, trigger or reformulation count.

## reddit-87311c2633df

> I don't think I'm explaining or describing what I want correctly. Let me try again:
> Say I have an album with 500 dog pictures in it. Google places those pictures in dated order of when they were taken. I want to group all 75 of the poodles together, but the poodle pics were taken days/weeks/months apart and are scattered all over the album, in dated order of when they were taken. How can I easily and quickly find all the poodles within that album and not have to page down over and over thru 500 pictures and check each one for the poodles? Because then I want to group the labs, then the Chihuahuas, then the German Shepherds.... Do you see what I'm saying? Like I said, doing CtrlF when I open the album and searching for poodles isn't working, it says there are 0 poodle pictures even though I'm looking at one at the top of the album.
> Hope I explained this better and hope someone has an answer. Thanks again!

Scope: `adjacent_known_item_retrieval`; reason: `known_item_with_precise_recall_failure`; cases: 1

AI-assisted unapproved draft. Not an independent human label. The initial 'Say I have' framing is hypothetical, but the later first-person CtrlF attempt and currently visible poodle ground a real album retrieval issue. Precise breed is recalled; scattered dates do not establish forgotten dates. Human decision recorded 2026-10-04: accept_real_episode_grounding. This scoped approval does not represent blanket approval of all fields or independent double-coding.

- `known_item_status`: `stated`; `"explicit"`
- `target_asset_type`: `stated`; `"photo"`
- `outcome`: `not_stated`; `null`
- `severity`: `not_stated`; `null`
- `reformulation_count`: `not_stated`; `null`
- `target_subjects`: `stated`; `[{"value": "pet_or_animal", "detail": "poodles"}]`
- `remembered_cues`: `stated`; `[{"value": "object_or_subject", "detail": null}]`
- `forgotten_information`: `not_stated`; `[]`
- `query_strategies`: `stated`; `[{"value": "single_keyword", "detail": null}]`
- `system_responses`: `stated`; `[{"value": "no_results", "detail": null}]`
- `workarounds`: `not_stated`; `[]`
- `impact_signals`: `not_stated`; `[]`
- `retrieval_trigger`: `not_stated`; `null`
- `exact_query`: `not_stated`; `null`
- `query_paraphrase`: `stated`; `"poodles"`

Evidence:

- `known_item_status` [676, 842): doing CtrlF when I open the album and searching for poodles isn't working, it says there are 0 poodle pictures even though I'm looking at one at the top of the album.
- `target_asset_type` [759, 841): there are 0 poodle pictures even though I'm looking at one at the top of the album
- `target_subjects` [771, 786): poodle pictures
- `remembered_cues` [714, 735): searching for poodles
- `query_strategies` [676, 842): doing CtrlF when I open the album and searching for poodles isn't working, it says there are 0 poodle pictures even though I'm looking at one at the top of the album.
- `system_responses` [751, 786): it says there are 0 poodle pictures

The counts 500/75 and proposed grouping of other breeds are illustrative, not independent episodes or measured corpus quantities. The field query_paraphrase records the reported search term, without presenting it as a delimited exact query. Zero CtrlF results are a system response; the ultimate retrieval/grouping outcome is unstated. Proposed manual paging is not treated as a completed workaround or time loss.

## reddit-bde62ddef9b5

> I backup all my photos on Google Photos. Their search feature allows me to type in situations I'm looking for. For example my 3rd used to listen to the weirdest white noise and I took a video of it once, but I can't remember when it was. I can type in "Show me videos of Suzie sleeping" and up it pops.

Scope: `core_incomplete_recall`; reason: `known_item_with_incomplete_recall`; cases: 1

AI-assisted unapproved draft. Not an independent human label. The author recalls a particular video but not when it was taken and describes successfully retrieving it with a natural-language query. Successful retrieval remains relevant to the discovery question. Sunayana approved the presented core/one-case summary on 2026-10-04: forgotten date, delimited natural-language query, successful retrieval, uncertain subject and no invented motive/impact/severity. This records approval of that summary, not additional unstated decisions, independent double-coding or adjudication.

- `known_item_status`: `stated`; `"explicit"`
- `target_asset_type`: `stated`; `"video"`
- `outcome`: `stated`; `"found"`
- `severity`: `not_stated`; `null`
- `reformulation_count`: `not_stated`; `null`
- `target_subjects`: `uncertain`; `[]`
- `remembered_cues`: `stated`; `[{"value": "activity", "detail": null}]`
- `forgotten_information`: `stated`; `[{"value": "exact_date", "detail": null}]`
- `query_strategies`: `stated`; `[{"value": "natural_language_description", "detail": null}]`
- `system_responses`: `stated`; `[{"value": "other", "detail": null}]`
- `workarounds`: `not_stated`; `[]`
- `impact_signals`: `not_stated`; `[]`
- `retrieval_trigger`: `not_stated`; `null`
- `exact_query`: `stated`; `"Show me videos of Suzie sleeping"`
- `query_paraphrase`: `not_stated`; `null`

Evidence:

- `known_item_status` [177, 202): I took a video of it once
- `target_asset_type` [177, 202): I took a video of it once
- `target_subjects` [123, 172): my 3rd used to listen to the weirdest white noise
- `remembered_cues` [253, 285): Show me videos of Suzie sleeping
- `forgotten_information` [208, 236): I can't remember when it was
- `query_strategies` [238, 302): I can type in "Show me videos of Suzie sleeping" and up it pops.
- `system_responses` [287, 301): and up it pops
- `outcome` [287, 301): and up it pops
- `exact_query` [253, 285): Show me videos of Suzie sleeping

Suzie and 'my 3rd' do not unambiguously establish a person versus another subject from this body alone; subject type remains uncertain. White noise is not treated as a retrieval trigger. No explicit impact or severity. 'Other' means the desired asset surfaces, since the response vocabulary has no successful-result member.

## reddit-c2c00b25a88b

> You know, I was so shocked to not be able to find pictures of my cats, I was trying to show a friend some pictures over the weekend but got no results. I remember being able to find such straightforward pictures with ease. I also tried using the Gallery app but it also has no search function so I was now forced to scroll down & look for the photos one-by-one. For the "most smartest" smartphone, this is so unnecessarily frustrating.

Scope: `adjacent_known_item_retrieval`; reason: `known_item_with_precise_recall_failure`; cases: 1

AI-assisted unapproved draft. Not an independent human label. The user recalls their cat pictures, receives no results, tries Gallery and resorts to manual scrolling to show a friend. No incomplete recall is described. Human decision recorded 2026-10-04: approve_severity. This scoped approval does not represent blanket approval of all fields or independent double-coding.

- `known_item_status`: `stated`; `"explicit"`
- `target_asset_type`: `stated`; `"photo"`
- `outcome`: `not_stated`; `null`
- `severity`: `stated`; `3`
- `reformulation_count`: `not_stated`; `null`
- `target_subjects`: `stated`; `[{"value": "pet_or_animal", "detail": "cats"}]`
- `remembered_cues`: `stated`; `[{"value": "object_or_subject", "detail": null}]`
- `forgotten_information`: `not_stated`; `[]`
- `query_strategies`: `stated`; `[{"value": "external_app_or_search", "detail": null}, {"value": "manual_scrolling", "detail": null}]`
- `system_responses`: `stated`; `[{"value": "no_results", "detail": null}, {"value": "other", "detail": null}]`
- `workarounds`: `stated`; `[{"value": "used_external_app", "detail": null}, {"value": "manual_scrolling", "detail": null}]`
- `impact_signals`: `stated`; `[{"value": "repeat_effort", "detail": null}]`
- `retrieval_trigger`: `stated`; `"show a friend some pictures over the weekend"`
- `exact_query`: `not_stated`; `null`
- `query_paraphrase`: `not_stated`; `null`

Evidence:

- `known_item_status` [152, 222): I remember being able to find such straightforward pictures with ease.
- `target_asset_type` [330, 360): look for the photos one-by-one
- `target_subjects` [50, 69): pictures of my cats
- `remembered_cues` [50, 69): pictures of my cats
- `query_strategies` [223, 361): I also tried using the Gallery app but it also has no search function so I was now forced to scroll down & look for the photos one-by-one.
- `system_responses` [132, 150): but got no results
- `system_responses` [246, 292): Gallery app but it also has no search function
- `workarounds` [223, 361): I also tried using the Gallery app but it also has no search function so I was now forced to scroll down & look for the photos one-by-one.
- `impact_signals` [223, 361): I also tried using the Gallery app but it also has no search function so I was now forced to scroll down & look for the photos one-by-one.
- `severity` [223, 361): I also tried using the Gallery app but it also has no search function so I was now forced to scroll down & look for the photos one-by-one.
- `retrieval_trigger` [71, 131): I was trying to show a friend some pictures over the weekend

Multiple paths and forced item-by-item browsing support repeat_effort and rubric severity 3. No elapsed time is stated, so time_loss is absent. The initial exact query/keyword and eventual outcome are not stated. Frustration alone is not coded as distress.

## youtube-17fd27447275

> Lost my oldest photos

Scope: `out_of_scope`; reason: `insufficient_evidence_for_a_case`; cases: 0

AI-assisted unapproved draft. Not an independent human label. 'Lost my oldest photos' establishes neither a specific remembered target nor a retrieval attempt; it could refer to loss or inability to retrieve. Do not infer deletion, backup or incomplete recall. A broad prefilter should retain this ambiguous short text. Human decision recorded 2026-10-04: approve_exclusion_proposal. This scoped approval does not represent blanket approval of all fields or independent double-coding.

