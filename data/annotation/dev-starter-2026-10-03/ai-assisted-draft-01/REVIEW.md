# Ten development annotation drafts for approval

These are source-grounded AI-assisted proposals, not independent human gold labels. No prediction file was read for this drafting task. Earlier conversation/selection context exists, so this is not claimed as a blinded review.

10 documents: 2 core, 3 adjacent, 5 out of scope; 5 proposed cases. All human approvals remain pending. The original pack, official gold files and splits are unchanged. The two manifest-designated double-code documents still require independent human reviews; approval of this AI draft does not satisfy that requirement.

Read the source and proposed values below. Approve or request changes by document ID. In particular, confirm the Memories navigation exclusion, the poodle example's real-world grounding, the short YouTube exclusion and the cat case's severity. Approval must retain AI-assistance provenance. Do not emit these drafts as official gold automatically.

## google_support-2a080da4b930

Source: https://support.google.com/photos/thread/244617564?hl=en

### Source text

> I'm trying to search for one of my family in a Google photos album. It is not a shared album. It seems you can't search for a face within a specific album, which means I have to scroll through hundreds of photos to find the one I want. Any tips?

### Proposed document label

- Scope: `adjacent_known_item_retrieval`
- Reason: `known_item_retrieval_journey_described`
- Prefilter should pass: `true`
- Expected cases: 1

The user wants a particular family photo inside an album and describes unavailable face search. No forgotten or approximate cue is stated.

Approval points:

- Confirm requested face-search approach versus an actual search attempt.
- Confirm the hedged album limitation's observation status.

### Proposed case fields

- `known_item_status`: `stated`; value `"explicit"`
- `target_asset_type`: `stated`; value `"photo"`
- `outcome`: `not_stated`; value `null`
- `severity`: `not_stated`; value `null`
- `reformulation_count`: `not_stated`; value `null`
- `target_subjects`: `stated`; value `[{"value": "person", "detail": "one of my family"}]`
- `remembered_cues`: `stated`; value `[{"value": "relationship", "detail": null}]`
- `forgotten_information`: `not_stated`; value `[]`
- `query_strategies`: `stated`; value `[{"value": "person_or_face_search", "detail": null}]`
- `system_responses`: `uncertain`; value `[{"value": "filter_or_scope_mismatch", "detail": null}]`
- `workarounds`: `not_stated`; value `[]`
- `impact_signals`: `not_stated`; value `[]`
- `retrieval_trigger`: `not_stated`; value `null`
- `exact_query`: `not_stated`; value `null`
- `query_paraphrase`: `not_stated`; value `null`

Supporting continuous source quotes:

- `known_item_status` [212, 234): to find the one I want
- `target_asset_type` [178, 234): scroll through hundreds of photos to find the one I want
- `target_subjects` [25, 41): one of my family
- `remembered_cues` [25, 41): one of my family
- `query_strategies` [94, 154): It seems you can't search for a face within a specific album
- `system_responses` [94, 154): It seems you can't search for a face within a specific album

Face search is the requested approach, not a reported exact query. 'Have to scroll' describes the required alternative; completed scrolling, time consumed and final outcome are not established. The trigger is not stated. The scope limitation is hedged ('It seems'), so the reported system behavior is uncertain.

Human decision: pending. Reviewer check answers: pending.

## google_support-4f34e2312ca6

Source: https://support.google.com/photos/thread/413671839?hl=en

### Source text

> I went to Google Photos to look back at old photos and videos, but suddenly they all disappeared. I'm absolutely sure I didn't delete them, and no one has accessed my account. However, one thing that puzzles me is that I recently bought a tablet and connected it to the account where the photos and videos disappeared. It seems like it was linked to Google Photos. So I disconnected the tablet because I wanted to back up photos only to my phone. After that, when I checked my account again, all the old photos and videos from several years ago were gone

### Proposed document label

- Scope: `out_of_scope`
- Reason: `storage_backup_or_sync`
- Prefilter should pass: `false`
- Expected cases: 0

Bulk photos/videos disappear after connecting and disconnecting a tablet/account. This is a data availability/backup story, with no particular remembered item or retrieval journey. Deletion is not confirmed.

Human decision: pending. Reviewer check answers: pending.

## google_support-5b2ec98df32b

Source: https://support.google.com/photos/thread/167179917?hl=en

### Source text

> My photo memories come up and I can see randomly but how do I go back to view them?

### Proposed document label

- Scope: `out_of_scope`
- Reason: `casual_browsing_without_known_target`
- Prefilter should pass: `true`
- Expected cases: 0

The user asks how to revisit randomly displayed photo memories. The body identifies no particular photo or remembered episode to retrieve. A broad high-recall screen should retain this ambiguous navigation request for classification.

Approval points:

- Borderline: approve out-of-scope only if general revisiting of Memories is not a sufficiently specific known target. Adjacent is the alternative; no incomplete recall is stated.
- Manifest requires an independent second human review.

Human decision: pending. Reviewer check answers: pending.

## google_support-8c6ab430fbee

Source: https://support.google.com/photos/thread/178895995?hl=en

### Source text

> I backed up new photos for my google account and when they finished backing up i opened the google photos app and 90% of my old photos were not there and I can't find them in the trash section or anywhere in the google account
> 
> I tried many thing and still can't find them, i need help because these photos are so important to me and they disappeared suddenly.

### Proposed document label

- Scope: `out_of_scope`
- Reason: `storage_backup_or_sync`
- Prefilter should pass: `false`
- Expected cases: 0

The source describes 90% of old photos disappearing after backup, including absence from trash/account. This is bulk backup/data availability, rather than retrieval of a particular remembered item. The source does not establish actual deletion.

Human decision: pending. Reviewer check answers: pending.

## play_store-fb8c41525287

Source: https://play.google.com/store/apps/details?id=com.google.android.apps.photos&hl=en_IN

### Source text

> suddenly there are issues with photos disappearing after editing. if you manage to find them and reopen them, edit/share/ask buttons on the bottom no longer function.

### Proposed document label

- Scope: `out_of_scope`
- Reason: `editing_sharing_or_printing`
- Prefilter should pass: `false`
- Expected cases: 0

Generic disappearing-after-editing and nonfunctional edit/share/ask controls, without a particular known target or a personal retrieval episode. The word 'find' does not establish a retrieval case.

Human decision: pending. Reviewer check answers: pending.

## reddit-0d477b54fb9b

Source: https://www.reddit.com/r/googlephotos/comments/xl693t/is_there_a_way_to_search_google_photos_using_a/

### Source text

> I have a recent photo that has something very distinct in it. I am Trying to find an older photo I have of that same item but I have so many photos I can't find it and I don't remember when I took the photo. I was wondering if I could search Google photos on my phone to try to find a match to the current photo. Hope that makes sense. Thanks in advance!

### Proposed document label

- Scope: `core_incomplete_recall`
- Reason: `known_item_with_incomplete_recall`
- Prefilter should pass: `true`
- Expected cases: 1

The user explicitly has an older photo of the same item but cannot find it and cannot remember when it was taken. Their proposed reference-photo search is not reported as performed.

Approval points:

- Confirm mapping nonspecific forgotten 'when' to exact_date.

### Proposed case fields

- `known_item_status`: `stated`; value `"explicit"`
- `target_asset_type`: `stated`; value `"photo"`
- `outcome`: `stated`; value `"not_found"`
- `severity`: `not_stated`; value `null`
- `reformulation_count`: `not_stated`; value `null`
- `target_subjects`: `not_stated`; value `[]`
- `remembered_cues`: `stated`; value `[{"value": "object_or_subject", "detail": null}]`
- `forgotten_information`: `stated`; value `[{"value": "exact_date", "detail": null}]`
- `query_strategies`: `not_stated`; value `[]`
- `system_responses`: `not_stated`; value `[]`
- `workarounds`: `not_stated`; value `[]`
- `impact_signals`: `not_stated`; value `[]`
- `retrieval_trigger`: `not_stated`; value `null`
- `exact_query`: `not_stated`; value `null`
- `query_paraphrase`: `not_stated`; value `null`

Supporting continuous source quotes:

- `known_item_status` [82, 121): an older photo I have of that same item
- `target_asset_type` [82, 121): an older photo I have of that same item
- `remembered_cues` [82, 121): an older photo I have of that same item
- `forgotten_information` [168, 206): I don't remember when I took the photo
- `outcome` [126, 163): I have so many photos I can't find it

The source states a failed search for the item, but not a specific system response or executed image-search strategy. 'When' is coded as exact_date; it does not establish forgotten time-of-day. The item is unspecified, so no subject type is inferred. No stated impact, severity, trigger or reformulation count.

Human decision: pending. Reviewer check answers: pending.

## reddit-87311c2633df

Source: https://www.reddit.com/r/googlephotos/comments/1vcu3cs/comment/p2kn53g/

### Source text

> I don't think I'm explaining or describing what I want correctly. Let me try again:
> Say I have an album with 500 dog pictures in it. Google places those pictures in dated order of when they were taken. I want to group all 75 of the poodles together, but the poodle pics were taken days/weeks/months apart and are scattered all over the album, in dated order of when they were taken. How can I easily and quickly find all the poodles within that album and not have to page down over and over thru 500 pictures and check each one for the poodles? Because then I want to group the labs, then the Chihuahuas, then the German Shepherds.... Do you see what I'm saying? Like I said, doing CtrlF when I open the album and searching for poodles isn't working, it says there are 0 poodle pictures even though I'm looking at one at the top of the album.
> Hope I explained this better and hope someone has an answer. Thanks again!

### Proposed document label

- Scope: `adjacent_known_item_retrieval`
- Reason: `known_item_with_precise_recall_failure`
- Prefilter should pass: `true`
- Expected cases: 1

The initial 'Say I have' framing is hypothetical, but the later first-person CtrlF attempt and currently visible poodle ground a real album retrieval issue. Precise breed is recalled; scattered dates do not establish forgotten dates.

Approval points:

- Confirm later first-person evidence sufficiently grounds the initially hypothetical album example.

### Proposed case fields

- `known_item_status`: `stated`; value `"explicit"`
- `target_asset_type`: `stated`; value `"photo"`
- `outcome`: `not_stated`; value `null`
- `severity`: `not_stated`; value `null`
- `reformulation_count`: `not_stated`; value `null`
- `target_subjects`: `stated`; value `[{"value": "pet_or_animal", "detail": "poodles"}]`
- `remembered_cues`: `stated`; value `[{"value": "object_or_subject", "detail": null}]`
- `forgotten_information`: `not_stated`; value `[]`
- `query_strategies`: `stated`; value `[{"value": "single_keyword", "detail": null}]`
- `system_responses`: `stated`; value `[{"value": "no_results", "detail": null}]`
- `workarounds`: `not_stated`; value `[]`
- `impact_signals`: `not_stated`; value `[]`
- `retrieval_trigger`: `not_stated`; value `null`
- `exact_query`: `not_stated`; value `null`
- `query_paraphrase`: `stated`; value `"poodles"`

Supporting continuous source quotes:

- `known_item_status` [676, 842): doing CtrlF when I open the album and searching for poodles isn't working, it says there are 0 poodle pictures even though I'm looking at one at the top of the album.
- `target_asset_type` [759, 841): there are 0 poodle pictures even though I'm looking at one at the top of the album
- `target_subjects` [771, 786): poodle pictures
- `remembered_cues` [714, 735): searching for poodles
- `query_strategies` [676, 842): doing CtrlF when I open the album and searching for poodles isn't working, it says there are 0 poodle pictures even though I'm looking at one at the top of the album.
- `system_responses` [751, 786): it says there are 0 poodle pictures

The counts 500/75 and proposed grouping of other breeds are illustrative, not independent episodes or measured corpus quantities. The field query_paraphrase records the reported search term, without presenting it as a delimited exact query. Zero CtrlF results are a system response; the ultimate retrieval/grouping outcome is unstated. Proposed manual paging is not treated as a completed workaround or time loss.

Human decision: pending. Reviewer check answers: pending.

## reddit-bde62ddef9b5

Source: https://www.reddit.com/r/Parents/comments/1qr2y7i/comment/o2nyagr/

### Source text

> I backup all my photos on Google Photos. Their search feature allows me to type in situations I'm looking for. For example my 3rd used to listen to the weirdest white noise and I took a video of it once, but I can't remember when it was. I can type in "Show me videos of Suzie sleeping" and up it pops.

### Proposed document label

- Scope: `core_incomplete_recall`
- Reason: `known_item_with_incomplete_recall`
- Prefilter should pass: `true`
- Expected cases: 1

The author recalls a particular video but not when it was taken and describes successfully retrieving it with a natural-language query. Successful retrieval remains relevant to the discovery question.

Approval points:

- Confirm forgotten 'when' coding and uncertain subject type.

### Proposed case fields

- `known_item_status`: `stated`; value `"explicit"`
- `target_asset_type`: `stated`; value `"video"`
- `outcome`: `stated`; value `"found"`
- `severity`: `not_stated`; value `null`
- `reformulation_count`: `not_stated`; value `null`
- `target_subjects`: `uncertain`; value `[]`
- `remembered_cues`: `stated`; value `[{"value": "activity", "detail": null}]`
- `forgotten_information`: `stated`; value `[{"value": "exact_date", "detail": null}]`
- `query_strategies`: `stated`; value `[{"value": "natural_language_description", "detail": null}]`
- `system_responses`: `stated`; value `[{"value": "other", "detail": null}]`
- `workarounds`: `not_stated`; value `[]`
- `impact_signals`: `not_stated`; value `[]`
- `retrieval_trigger`: `not_stated`; value `null`
- `exact_query`: `stated`; value `"Show me videos of Suzie sleeping"`
- `query_paraphrase`: `not_stated`; value `null`

Supporting continuous source quotes:

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

Human decision: pending. Reviewer check answers: pending.

## reddit-c2c00b25a88b

Source: https://www.reddit.com/r/googlephotos/comments/1px47il/comment/nwjfax6/

### Source text

> You know, I was so shocked to not be able to find pictures of my cats, I was trying to show a friend some pictures over the weekend but got no results. I remember being able to find such straightforward pictures with ease. I also tried using the Gallery app but it also has no search function so I was now forced to scroll down & look for the photos one-by-one. For the "most smartest" smartphone, this is so unnecessarily frustrating.

### Proposed document label

- Scope: `adjacent_known_item_retrieval`
- Reason: `known_item_with_precise_recall_failure`
- Prefilter should pass: `true`
- Expected cases: 1

The user recalls their cat pictures, receives no results, tries Gallery and resorts to manual scrolling to show a friend. No incomplete recall is described.

Approval points:

- Severity 3 is a rubric judgment from demonstrated alternative paths/manual browsing; review this ordinal choice.

### Proposed case fields

- `known_item_status`: `stated`; value `"explicit"`
- `target_asset_type`: `stated`; value `"photo"`
- `outcome`: `not_stated`; value `null`
- `severity`: `stated`; value `3`
- `reformulation_count`: `not_stated`; value `null`
- `target_subjects`: `stated`; value `[{"value": "pet_or_animal", "detail": "cats"}]`
- `remembered_cues`: `stated`; value `[{"value": "object_or_subject", "detail": null}]`
- `forgotten_information`: `not_stated`; value `[]`
- `query_strategies`: `stated`; value `[{"value": "external_app_or_search", "detail": null}, {"value": "manual_scrolling", "detail": null}]`
- `system_responses`: `stated`; value `[{"value": "no_results", "detail": null}, {"value": "other", "detail": null}]`
- `workarounds`: `stated`; value `[{"value": "used_external_app", "detail": null}, {"value": "manual_scrolling", "detail": null}]`
- `impact_signals`: `stated`; value `[{"value": "repeat_effort", "detail": null}]`
- `retrieval_trigger`: `stated`; value `"show a friend some pictures over the weekend"`
- `exact_query`: `not_stated`; value `null`
- `query_paraphrase`: `not_stated`; value `null`

Supporting continuous source quotes:

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

Human decision: pending. Reviewer check answers: pending.

## youtube-17fd27447275

Source: https://www.youtube.com/watch?v=TlYoYKBC7O0&lc=UgwEPLUPB_DJQ-NwLr94AaABAg

### Source text

> Lost my oldest photos

### Proposed document label

- Scope: `out_of_scope`
- Reason: `insufficient_evidence_for_a_case`
- Prefilter should pass: `true`
- Expected cases: 0

'Lost my oldest photos' establishes neither a specific remembered target nor a retrieval attempt; it could refer to loss or inability to retrieve. Do not infer deletion, backup or incomplete recall. A broad prefilter should retain this ambiguous short text.

Approval points:

- Very short ambiguous text: confirm exclusion for insufficient evidence, rather than assume a loss mechanism.
- Manifest requires an independent second human review.

Human decision: pending. Reviewer check answers: pending.

