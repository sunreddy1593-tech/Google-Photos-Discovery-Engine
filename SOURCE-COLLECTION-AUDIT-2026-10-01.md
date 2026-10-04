# Free collection route audit — 2026-10-01

## Outcome and scope

This reassessment is authorized by the project owner. It replaces the blanket
"permanently closed" conclusions for these sources with route-specific findings.
It does not relax access restrictions, robots.txt, or applicable source terms.

- **Google Photos community: technically available but access requirements unresolved.**
  Supplied thread URLs are not robots-disallowed; permission for this automated
  collection has not been established. Source-native search and internal API
  paths are robots-disallowed. Current thread fetching was not exercised.
- **Google Play reviews: blocked for the inspected routes.** The official API
  requires publisher access; the open-source collectors use a robots-disallowed
  web RPC. No suitable permitted alternative was established.
- **Apple App Store reviews: blocked for the inspected routes.** The official
  API requires App Store Connect access; the inspected public RSS collector
  uses a robots-disallowed path. No suitable permitted alternative was established.

**No source was exercised successfully.** Data requests and collected records:
Google community **0 / 0**, Google Play **0 / 0**, Apple **0 / 0**. The authorized
ceiling was three data requests and five records per source; these were ceilings,
not targets. Probes did not proceed past the access review. Documentation,
robots files, and open-source code were inspected online; those are not corpus
data requests. No search snippet or AI summary was imported as a user record.

No packages were installed or collectors executed. There were no paid services,
model calls, proxies, identity rotation, login attempts, CAPTCHA solving, or
anti-bot workarounds. No adapter or adapter test was manufactured for an
unexercised route. No collector dry-run is claimed by this audit.

## Google Photos community

### Mechanism and permission

The existing ADR-22 records a historical frontend observation of
`https://support.google.com/photos/thread/{threadId}?msgid={replyId}`.
This audit did not re-fetch threads or reconfirm that reply-focus behavior.
No documented public community export/data API was identified in the official
documentation search. This is a search result, not proof that no such API exists.

The [current robots file](https://support.google.com/robots.txt) was fetched
directly with HTTP 200. Its wildcard-agent rules disallow `/*/search`, `/*/api`,
`/*/apis`, `/*/bin/search.py`, `/bin/search.py`, `/bin/search.go`, and
`/*/forum-attachment`. They do not disallow `/photos/thread/...` or
`/photos/community`. A failure to load the robots file through the web research
tool was not a source HTTP denial; the direct policy-file fetch succeeded.

The [Google Terms](https://policies.google.com/terms?hl=en-US) prohibit automated
access that violates machine-readable instructions. The reference to scraping
others' content appears in the suspension clause's context of conduct causing
harm or liability. The old ADR treated that example as an unconditional,
standalone ban. That interpretation was too broad. Conversely, an undisallowed
path and public visibility do not establish permission for this project's
automated collection and reuse. No explicit permission basis was established
here; collection remains unresolved, rather than permanently prohibited.

### Discovery is separate from fetching

- **Supplied URLs:** a narrowly bounded fetcher could target thread pages if
  the permission basis is resolved. No source search would be necessary.
- **Discovery:** `/photos/search?...` and internal `/photos/api...` routes
  cannot be used under the current robots requirements. The community index is
  not disallowed, but its pagination, coverage, and collection permission were
  not verified. External search results could only supply candidate links;
  their snippets are not original posts.

No dedicated maintained Google Photos community collector was established in
this bounded search. [Scrapy](https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#module-scrapy.downloadermiddlewares.robotstxt)
is an open-source HTML fetching candidate, not a Photos-specific parser or a
permission grant. Its robots middleware must be enabled with
`ROBOTSTXT_OBEY`; using a framework would not resolve the source terms or prove
that full threads can be retrieved. No Scrapy spider was installed or run.

### Provenance and reliability still to verify

A future qualifying probe must retrieve original post/reply bodies, native
thread and message IDs, source links, and explicit dates, with each reply kept
separate and connected to its parent. Native IDs must not be invented from
display order. Accepted answers and expert advice must not be relabelled as
first-person user experience. Visible reply counts, loaded replies, and
unvisited pages must be distinguished. No completeness or pagination limit
has been measured in this audit.

## Google Photos on Google Play

### Official and open-source routes

The [official Reply to Reviews documentation](https://developers.google.com/android-publisher/reply-to-reviews)
describes access to the publisher's app using authorized credentials and the
Reply to reviews permission. The endpoint is
`GET https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{packageName}/reviews`.
It is not an unauthenticated API for arbitrary apps. This project has not
established publisher access to Google Photos (`com.google.android.apps.photos`).
The documented recent-review window also limits this API; it is not a full
historical export route for a third-party researcher.

Two free collector implementations were inspected, without execution:

- [JoMingyu/google-play-scraper request definitions](https://github.com/JoMingyu/google-play-scraper/blob/master/google_play_scraper/constants/request.py),
  [review loop](https://github.com/JoMingyu/google-play-scraper/blob/master/google_play_scraper/features/reviews.py),
  and [field mapping](https://github.com/JoMingyu/google-play-scraper/blob/master/google_play_scraper/constants/element.py).
- [app-reviews Google Play implementation](https://github.com/0xfirattamur/app-reviews/blob/main/src/app_reviews/googleplay/web.py).

Both use `POST https://play.google.com/_/PlayStoreUi/data/batchexecute`
with RPC `oCPfdb`, language/country parameters, and continuation tokens. That is
an undocumented website RPC, not the official publisher API. The
[current Play robots file](https://play.google.com/robots.txt) disallows `/_`,
`/store/getreviews`, and `/store/search` for the wildcard user-agent. Thus this
RPC is blocked by the project's access requirements. **No RPC probe was sent.**
Changing libraries would still use the same restricted endpoint.

### Provenance and reliability from code, not live records

The JoMingyu mapping exposes native review ID, body, author name, rating,
review date, app version, and developer reply text/date. These are promising
provenance fields, not verified collection. A review permalink is not included
in that mapping; an app listing link must not be misrepresented as a verified
review-specific link. Developer responses need their own speaker attribution.
Its timestamp conversion uses a naive local datetime, requiring explicit
timezone treatment before `CollectedDocument` import.

Its review loop catches broad exceptions and may return an empty or partial
result, which cannot be accepted as a successful zero-result collection. The
inspected source's `MAX_COUNT_EACH_FETCH` is 4500; README examples describe a
different limit. Neither is a verified vendor page-size guarantee.

The app-reviews implementation requests pages of 200 with continuation
cursors and parses timestamps as UTC. It has explicit parsing failures, but
also depends on positional arrays in the undocumented response. Its country
and language settings do not prove a reviewer's country or demographics.
Pagination completeness and stable behavior were not exercised.

## Google Photos on the Apple App Store

### Official and open-source routes

Apple's [Customer Reviews documentation](https://developer.apple.com/documentation/appstoreconnectapi/customer-reviews)
describes reviews for an app accessible through the caller's App Store Connect
account. The route is
`GET https://api.appstoreconnect.apple.com/v1/apps/{id}/customerReviews`.
The project has not established that access for Google Photos. No credentials
were requested or tested.

The free [app-reviews RSS implementation](https://github.com/0xfirattamur/app-reviews/blob/main/src/app_reviews/appstore/rss.py)
uses
`GET https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/page={page}/json`
and can fall back to the corresponding `/xml` route. Google Photos' public
App Store ID is `962194608`; its [listing](https://apps.apple.com/us/app/google-photos-backup-edit/id962194608)
is a source locator, not evidence that review collection is permitted.

The [current iTunes robots file](https://itunes.apple.com/robots.txt) disallows
`/*/rss/*` for the wildcard user-agent. Both formats match. **Neither was
probed.** A crawler-specific allowance does not apply to our collector.

The [App Store website robots file](https://apps.apple.com/robots.txt) also
disallows `/WebObjects/*`, `/api/*`, `/includes/*`, and `/v1/*`. Product-page
HTML is not a verified alternative review feed. The same library's
[product-page implementation](https://github.com/0xfirattamur/app-reviews/blob/main/src/app_reviews/appstore/product_page.py)
parses version history, not customer review pagination.

[Apple website terms](https://www.apple.com/legal/internet-services/terms/site.html)
restrict automated acquisition outside the means purposely made available.
[US Media Services terms](https://www.apple.com/legal/internet-services/itunes/us/terms.html)
also contain automated collection restrictions. The project's applicable
regional/service terms would need resolution for any different route; the US
document alone does not settle terms for an India-based researcher. The
robots restriction is already decisive for the inspected RSS route.

### Provenance and reliability from code, not live records

The RSS parser exposes entry ID, title, body, author, rating, version, and an
`updated` timestamp. Updated time must not silently become publication time.
No review-specific permalink or developer-reply relationship is established
by that mapping. Storefront and endpoint identity must accompany native IDs;
cross-endpoint ID equivalence must not be assumed.

The library assumes ten pages of fifty entries, an undocumented library
limit rather than a measured result here or a vendor completeness promise.
It can try XML after an unusable successful JSON response; each such fetch
would consume another request. Its label helper strips text and normalizes
line endings, so a future adapter would need to preserve the original received
body instead of treating the helper's transformed body as verbatim evidence.
Malformed entries and partial pagination must be explicit failures/limitations.

ADR-22's recorded empty-feed observations from 2026-09-21 remain historical
claims, not fresh findings. They do not prove that all RSS feeds always return
zero or that every contrary report is wrong. This audit neither confirms nor
denies current feed contents, because it stopped at robots restrictions.

## Integration decision and conditions for reconsideration

The existing `src/models/collected_document.py`, `src/core/ids.py`, and
`src/collect/workbook.py` were inspected. Collection already has immutable
verbatim text, source IDs/URLs, timezone-aware dates, salted author hashes,
and import-time duplicate checks; normalization and corpus deduplication are
later stages. No new collection framework is needed.

No route met the prerequisite for the requested successful-route adapter.
Accordingly this change adds documentation only, not a collector that returns
empty data or advertises an unverified capability. Before an adapter is added:

1. Record a route-specific permission basis and current robots result. A
   publisher-authorized export, explicit permission, or a documented permitted
   public route could change the decision. Mere library availability cannot.
2. Exercise that qualifying route within the authorized three-request,
   five-record ceiling. Count redirects, retries and format fallbacks; stop on
   access restrictions without changing identity. Preserve original provenance
   and state partial coverage rather than silently dropping failures.
3. Adapt into the existing contracts/import persistence, reusing salted author
   hashing and stable source IDs. Deduplicate repeated items without rewriting
   history; preserve parent relationships and unknown dates honestly.
4. Mock request caps, pagination stops, duplicate handling, author privacy,
   explicit blocked/error states, and a dry-run making zero requests and
   writing no records. Only then advertise exercised collection.

The shared collection CLI, source configuration, and concurrent YouTube
implementation were not edited by this audit. Old configuration notes may
still contain superseded blanket wording; they are not permission findings
and this audit does not enable those sources. Historical data, labels, split,
and holdout were not read or changed. No commit or push was performed.

## Verification record

Documentation and repository code inspection only. Open-source links identify
the branches inspected on 2026-10-01, not immutable release guarantees. No
data endpoint or production collector was exercised, and no extraction or
collection quality result follows. Runtime tests are not claimed for this
documentation-only change. `git diff --check` passed (exit 0); the new untracked
audit separately passed trailing-whitespace and local-reference checks.
`git status --short` was inspected and includes existing extraction changes
and concurrent YouTube changes in addition to this audit's seven documentation
files. Those unrelated changes are not attributed to this task. The separate
YouTube work is outside this audit's verification scope.
