"""Fixed public feed catalog. Descriptive roles and inherited priors are uncalibrated.

Dated qualification: HTTP/parser compatibility on2026-10-29. Availability,
source agreement and editorial affiliation do not establish factual accuracy.
UN/WHO/Lyn Alden remain explicit opt-in candidates for clock/context limitations.
"""

RSS_FEEDS = [{'source': 'bbc_mideast',
  'url': 'https://feeds.bbci.co.uk/news/world/middle_east/rss.xml',
  'display_name': 'BBC News',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 4,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'the_war_zone',
  'url': 'https://www.twz.com/feed',
  'display_name': 'TWZ',
  'role': 'specialist_reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 4,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'aljazeera',
  'url': 'https://www.aljazeera.com/xml/rss/all.xml',
  'display_name': 'Al Jazeera',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'times_of_israel',
  'url': 'https://www.timesofisrael.com/feed/',
  'display_name': 'The Times of Israel',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'rfi',
  'url': 'https://www.rfi.fr/en/rss',
  'display_name': 'RFI - All the news from France, Europe, Africa and the rest of the world.',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'defense_one',
  'url': 'https://www.defenseone.com/rss/all/',
  'display_name': 'Defense One - All Content',
  'role': 'specialist_reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'guardian_mideast',
  'url': 'https://www.theguardian.com/world/middleeast/rss',
  'display_name': 'Middle East and north Africa | The Guardian',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 4,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'dw_world',
  'url': 'https://rss.dw.com/xml/rss-en-world',
  'display_name': 'World | Deutsche Welle',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'middle_east_eye',
  'url': 'https://www.middleeasteye.net/rss',
  'display_name': 'Section Feed',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 2,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'jpost',
  'url': 'https://m.jpost.com/rss/rssfeedsisraelnews.aspx',
  'display_name': 'JPost.com - Israel News: Updates on Israeli Politics, Security & Diplomacy | The '
                  'Jerusalem Post',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'dropsitenews_rss',
  'url': 'https://www.dropsitenews.com/feed',
  'display_name': 'Drop Site News',
  'role': 'reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 4,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'war_on_rocks',
  'url': 'https://warontherocks.com/feed/',
  'display_name': 'War on the Rocks',
  'role': 'analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 5,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'oilprice',
  'url': 'https://oilprice.com/rss/main',
  'display_name': 'Oilprice.com',
  'role': 'market_reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'freightwaves',
  'url': 'https://www.freightwaves.com/news/feed',
  'display_name': 'news - FreightWaves',
  'role': 'logistics_reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 4,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'hellenic_shipping',
  'url': 'https://www.hellenicshippingnews.com/feed/',
  'display_name': 'Hellenic Shipping News Worldwide',
  'role': 'shipping_reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'splash247',
  'url': 'https://splash247.com/feed/',
  'display_name': 'Splash247',
  'role': 'shipping_reporting',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': 3,
  'prior_status': 'historical_uncalibrated',
  'bias_notes': 'Historical registry entry. Any numerical prior is inherited and uncalibrated; it is '
                'not measured accuracy, independence, or verification. Feed availability was observed '
                'on 2026-10-29 only.'},
 {'source': 'chris_hedges_candidate',
  'url': 'https://chrishedges.substack.com/feed',
  'display_name': 'The Chris Hedges Report',
  'role': 'commentary_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'greenwald_candidate',
  'url': 'https://greenwald.substack.com/feed',
  'display_name': 'Glenn Greenwald',
  'role': 'commentary_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'caitlin_johnstone_candidate',
  'url': 'https://caitlinjohnstone.com.au/feed/',
  'display_name': 'Caitlin Johnstone',
  'role': 'commentary_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'consortium_news_candidate',
  'url': 'https://consortiumnews.com/feed/',
  'display_name': 'Consortium News',
  'role': 'reporting_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'grayzone_candidate',
  'url': 'https://thegrayzone.com/feed/',
  'display_name': 'The Grayzone',
  'role': 'reporting_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'antiwar_blog_candidate',
  'url': 'https://www.antiwar.com/blog/feed/',
  'display_name': 'Antiwar.com Blog',
  'role': 'commentary_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'middle_east_monitor_candidate',
  'url': 'https://www.middleeastmonitor.com/feed/',
  'display_name': 'Middle East Monitor',
  'role': 'reporting_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': '972_magazine_candidate',
  'url': 'https://www.972mag.com/feed/',
  'display_name': '+972 Magazine',
  'role': 'reporting_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'democracy_now_candidate',
  'url': 'https://www.democracynow.org/democracynow.rss',
  'display_name': 'Democracy Now!',
  'role': 'reporting_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'responsible_statecraft_candidate',
  'url': 'https://responsiblestatecraft.org/feeds/feed.rss',
  'display_name': 'Responsible Statecraft',
  'role': 'commentary_and_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'un_news_candidate',
  'url': 'https://news.un.org/feed/subscribe/en/news/all/rss.xml',
  'display_name': 'UN News - Global perspective Human stories',
  'role': 'institutional',
  'languages': ['en'],
  'default_enabled': False,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Explicit opt-in only: future source clock observed; not repaired by retrieval.'},
 {'source': 'cpj_candidate',
  'url': 'https://cpj.org/feed/',
  'display_name': 'Committee to Protect Journalists',
  'role': 'institutional',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Default eligible for attributed report preservation; no claim of factual '
                    'accuracy.'},
 {'source': 'who_news_candidate',
  'url': 'https://www.who.int/rss-feeds/news-english.xml',
  'display_name': 'News (English) - World Health Organization',
  'role': 'institutional',
  'languages': ['en'],
  'default_enabled': False,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored posts, preserved with attribution. Role is descriptive, not an '
                'accuracy or independence rating. Dated HTTP/parser probe is not long-term availability '
                'or factual verification.',
  'admission_note': 'Explicit opt-in only: contextual health source, newest publication about19days old '
                    'at probe.'},
 {'source': 'peak_prosperity_candidate',
  'url': 'https://peakprosperity.com/feed/',
  'display_name': 'Peak Prosperity',
  'role': 'macro_and_geopolitical_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored analysis/context, not a breaking-incident fact feed. No calibrated '
                'accuracy/independence prior. Dated native-feed parser compatibility only.',
  'admission_note': 'Default eligible for attributed analysis/context posts; no claim of factual '
                    'verification or first-report speed.'},
 {'source': 'lyn_alden_candidate',
  'url': 'https://www.lynalden.com/feed/',
  'display_name': 'Lyn Alden',
  'role': 'macro_and_geopolitical_analysis',
  'languages': ['en'],
  'default_enabled': False,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored analysis/context, not a breaking-incident fact feed. No calibrated '
                'accuracy/independence prior. Dated native-feed parser compatibility only.',
  'admission_note': 'Explicit contextual opt-in: newest feed publication2026-07-15 at the2026-10-29 '
                    'probe. This does not establish author inactivity or other-platform freshness.'},
 {'source': 'gzero_candidate',
  'url': 'https://www.gzeromedia.com/feeds/feed.rss',
  'display_name': 'GZERO Media',
  'role': 'macro_and_geopolitical_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored analysis/context, not a breaking-incident fact feed. No calibrated '
                'accuracy/independence prior. Dated native-feed parser compatibility only.',
  'admission_note': 'Default eligible for attributed analysis/context posts; no claim of factual '
                    'verification or first-report speed.'},
 {'source': 'naked_capitalism_candidate',
  'url': 'https://www.nakedcapitalism.com/feed',
  'display_name': 'Naked Capitalism',
  'role': 'macro_and_geopolitical_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored analysis/context, not a breaking-incident fact feed. No calibrated '
                'accuracy/independence prior. Dated native-feed parser compatibility only.',
  'admission_note': 'Default eligible for attributed analysis/context posts; no claim of factual '
                    'verification or first-report speed.'},
 {'source': 'geopolitical_economy_candidate',
  'url': 'https://geopoliticaleconomy.com/feed/',
  'display_name': 'Geopolitical Economy Report',
  'role': 'macro_and_geopolitical_analysis',
  'languages': ['en'],
  'default_enabled': True,
  'reliability': None,
  'prior_status': 'unassessed',
  'bias_notes': 'Publisher-authored analysis/context, not a breaking-incident fact feed. No calibrated '
                'accuracy/independence prior. Dated native-feed parser compatibility only.',
  'admission_note': 'Default eligible for attributed analysis/context posts; no claim of factual '
                    'verification or first-report speed.'}]
