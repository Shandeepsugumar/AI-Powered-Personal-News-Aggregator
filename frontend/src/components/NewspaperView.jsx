import React from 'react';
import { ExternalLink, Video, FileText, Mail, Clock, AlertCircle, Newspaper, Bookmark } from 'lucide-react';

function formatTeletypeTime(isoString) {
  if (!isoString) return "FILED RECENTLY";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "FILED RECENTLY";
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `FILED AT ${hours}:${minutes}`;
  } catch {
    return "FILED RECENTLY";
  }
}

export default function NewspaperView({ stories, followedSources = [], isLoading, activeCategory, onResetCategory, onOpenSources }) {
  
  // Format source type badge
  const renderSourceBadge = (source) => {
    let prefix = "📰";
    let typeClass = "border-stone-700 bg-stone-100/80 text-stone-900";

    if (source.type === 'YOUTUBE') {
      prefix = "▶";
      typeClass = "border-red-900/60 bg-red-50/50 text-red-950";
    } else if (source.type === 'NEWSLETTER') {
      prefix = "✉";
      typeClass = "border-amber-900/60 bg-amber-50/50 text-amber-950";
    }

    return (
      <a
        key={source.name + source.url}
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-ticker border hover:bg-[#EFECE4] transition-colors ${typeClass}`}
      >
        <span>{prefix}</span>
        <span className="font-bold">{source.name}</span>
        <ExternalLink className="w-2.5 h-2.5 opacity-60 ml-0.5" />
      </a>
    );
  };

  // Stance indicator styled as printed wax / rubber stamp tag
  const renderStancePill = (stance) => {
    let stampColor = "border-stone-700 text-stone-800 bg-stone-100/40";
    if (stance === 'Positive') stampColor = "border-emerald-800 text-emerald-950 bg-emerald-50/60";
    if (stance === 'Negative') stampColor = "border-amber-900 text-amber-950 bg-amber-50/60";

    return (
      <span className={`text-[10px] font-mono uppercase tracking-wider font-bold px-1.5 py-0.5 border shadow-[1px_1px_0px_rgba(0,0,0,0.1)] ${stampColor}`}>
        [{stance} Stance]
      </span>
    );
  };

  // 1. Loading Typesetting Skeleton State
  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8 font-serif">
        <div className="text-center py-4 mb-8 bg-[#EFECE4] border border-[#262624]">
          <Newspaper className="w-6 h-6 animate-pulse text-[#1C1A17] mx-auto mb-2" />
          <p className="text-sm font-editorial-body italic text-[#1C1A17] font-semibold">
            ✦ Typesetting your personal broadsheet from followed dispatches... ✦
          </p>
        </div>

        {/* Skeleton Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-8 space-y-8">
            <div className="border-b-2 border-[#262624] pb-6">
              <div className="h-4 w-24 bg-[#E5E0D5] animate-shimmer mb-3"></div>
              <div className="h-10 w-full bg-[#E5E0D5] animate-shimmer mb-4"></div>
              <div className="h-24 w-full bg-[#EFECE4] animate-shimmer mb-4"></div>
              <div className="h-4 w-48 bg-[#E5E0D5] animate-shimmer"></div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="border-t border-[#D5CEC2] pt-4 space-y-2">
                <div className="h-4 w-20 bg-[#E5E0D5] animate-shimmer"></div>
                <div className="h-6 w-full bg-[#E5E0D5] animate-shimmer"></div>
                <div className="h-16 w-full bg-[#EFECE4] animate-shimmer"></div>
              </div>
              <div className="border-t border-[#D5CEC2] pt-4 space-y-2">
                <div className="h-4 w-20 bg-[#E5E0D5] animate-shimmer"></div>
                <div className="h-6 w-full bg-[#E5E0D5] animate-shimmer"></div>
                <div className="h-16 w-full bg-[#EFECE4] animate-shimmer"></div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-4 border-l border-[#D5CEC2] pl-6 space-y-6">
            <div className="h-6 w-32 bg-[#E5E0D5] animate-shimmer mb-4"></div>
            <div className="h-20 w-full bg-[#EFECE4] animate-shimmer"></div>
            <div className="h-20 w-full bg-[#EFECE4] animate-shimmer"></div>
          </div>
        </div>
      </div>
    );
  }

  // 2a. Zero wire outlets configured fallback
  if (followedSources && followedSources.length === 0) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="text-center py-28 border-y-2 border-stone-800 my-8 bg-[#F4EFE6]/70">
          <p className="font-mono text-xs uppercase tracking-widest text-stone-500 mb-2">✦ Editorial Bureau ✦</p>
          <h3 className="font-serif text-3xl font-bold uppercase tracking-wider text-stone-800 mb-3">
            No Wire Outlets Configured
          </h3>
          <p className="font-serif italic text-stone-600 max-w-md mx-auto text-sm leading-relaxed mb-4">
            Your personalized edition is empty. Click <strong>"MANAGE WIRE"</strong> to add YouTube creators, newsletters, or blogs.
          </p>
          {onOpenSources && (
            <button
              onClick={onOpenSources}
              className="px-5 py-2.5 bg-[#1C1A17] text-[#F8F5EE] text-xs font-ticker font-bold uppercase tracking-wider hover:bg-[#333] transition-colors cursor-pointer border border-[#262624]"
            >
              Open Wire Manager →
            </button>
          )}
        </div>
      </div>
    );
  }

  // 2b. Zero-state broadsheet notice when no dispatches match active wire
  if (!stories || stories.length === 0) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="text-center py-24 border-y-2 border-stone-800 my-8 bg-[#F4EFE6]/50">
          <p className="font-mono text-xs uppercase tracking-widest text-stone-500 mb-2">✦ Editorial Wire Notice ✦</p>
          <h3 className="font-serif text-3xl font-bold uppercase tracking-wide text-stone-800 mb-3">
            No Dispatches From Your Followed Wire
          </h3>
          <p className="font-serif italic text-stone-600 max-w-lg mx-auto text-sm leading-relaxed mb-6">
            None of the stories in this edition match your active wire subscriptions. Open <strong>"MANAGE WIRE"</strong> to subscribe to publications or enable your existing feeds.
          </p>
          {onOpenSources && (
            <button
              onClick={onOpenSources}
              className="px-5 py-2.5 bg-[#1C1A17] text-[#F8F5EE] text-xs font-ticker font-bold uppercase tracking-wider hover:bg-[#333] transition-colors cursor-pointer border border-[#262624]"
            >
              Open Wire Manager →
            </button>
          )}
        </div>
      </div>
    );
  }

  // 3. Filter stories by category
  const filteredStories = stories.filter(s => {
    if (activeCategory === 'ALL') return true;
    return s.category.toUpperCase() === activeCategory.toUpperCase();
  });

  // 4. Empty state when a specific category has 0 stories
  if (filteredStories.length === 0) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center text-[#1C1A17]">
        <div className="border-2 border-[#262624] p-8 sm:p-12 bg-[#EFECE4]/50 shadow-[4px_4px_0px_#262624]">
          <AlertCircle className="w-12 h-12 text-[#1C1A17] mx-auto mb-4 stroke-1" />
          <h2 className="text-2xl font-headline font-bold uppercase tracking-widest mb-2">The Telegraph Wire Is Silent</h2>
          <p className="font-editorial-body text-[#44403C] italic max-w-md mx-auto mb-6 text-base">
            No dispatches have crossed the telegraph wire for the <strong>{activeCategory}</strong> desk.
          </p>
          {activeCategory !== 'ALL' && (
            <button
              onClick={onResetCategory}
              className="px-5 py-2 bg-[#1C1A17] text-[#F8F5EE] text-xs font-ticker font-bold uppercase tracking-wider hover:bg-[#333] transition-colors cursor-pointer"
            >
              View Full Broadsheet ({stories.length} Dispatches)
            </button>
          )}
        </div>
      </div>
    );
  }

  // 5. Dynamic Story Partitioning:
  // Lead story using stories[0], sidebar dispatches using stories.slice(1, 4), and secondary grid columns using stories.slice(4)
  const leadStory = filteredStories[0];
  const sidebarStories = filteredStories.slice(1, 4);
  const secondaryStories = filteredStories.slice(4);

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 pb-20 text-[#1C1A17]">
      
      {/* SECTION 1: TOP BROADSHEET FOLD (Lead story + Sidebar briefs) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start border-b-2 border-[#262624] pb-10">
        
        {/* Main Column (8 cols): LEAD EDITORIAL STORY */}
        <div className="lg:col-span-8">
          {leadStory && (
            <article className="relative pr-0 lg:pr-4">
              
              {/* Lead Top Meta Ticker */}
              <div className="flex flex-wrap items-center gap-2 mb-3 text-xs border-b border-[#D5CEC2] pb-2">
                <span className="bg-[#1C1A17] text-[#F8F5EE] font-ticker font-bold uppercase px-2 py-0.5 tracking-widest text-[10px]">
                  LEAD REPORT · {leadStory.category}
                </span>
                {renderStancePill(leadStory.stance)}
                
                <span className="text-[#666059] flex items-center gap-1 ml-auto font-ticker text-[10px]">
                  <Clock className="w-3 h-3" />
                  <span>{formatTeletypeTime(leadStory.timestamp)}</span>
                </span>
              </div>

              {/* Lead Headline */}
              <h2 className="text-3xl sm:text-4xl md:text-5xl font-extrabold font-headline tracking-tight text-[#1C1A17] leading-[1.08] my-4 hover:text-[#333] transition-colors">
                {leadStory.sources?.[0]?.url ? (
                  <a href={leadStory.sources[0].url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                    {leadStory.headline}
                  </a>
                ) : (
                  leadStory.headline
                )}
              </h2>

              {/* Lead Story Image */}
              {leadStory.imageUrl && (
                <div className="my-4 border border-stone-800 p-1 bg-stone-100/60 shadow-inner">
                  <div className="relative overflow-hidden max-h-96">
                    <img
                      src={leadStory.imageUrl}
                      alt={leadStory.headline}
                      className="w-full h-full object-cover grayscale contrast-125 sepia-[0.20] hover:grayscale-0 transition-all duration-500"
                      onError={(e) => {
                        e.currentTarget.parentElement.parentElement.style.display = 'none';
                      }}
                    />
                  </div>
                  <figcaption className="text-[10px] font-mono uppercase tracking-widest text-stone-600 mt-1.5 flex justify-between px-1">
                    <span>Plate No. 1 · Wire Photogram</span>
                    <span>Source: {leadStory.sources?.[0]?.name || 'Press Bureau'}</span>
                  </figcaption>
                </div>
              )}

              {/* Lead Paragraph with authentic Drop Cap */}
              <p className="drop-cap text-[#1C1A17] text-lg sm:text-xl font-editorial-body leading-relaxed mb-6 text-justify">
                {leadStory.summary}
              </p>

              {/* Contributing Wire Channels Footer */}
              <div className="pt-3 border-t border-[#D5CEC2] flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-ticker font-bold uppercase text-[#57524D]">
                    Contributing Source:
                  </span>
                  {leadStory.sources?.map((s, i) => renderSourceBadge(s, i))}
                </div>
                <span className="text-[11px] font-editorial-body italic text-[#78716C]">
                  Synthesized via Editorial AI Desks
                </span>
              </div>
            </article>
          )}
        </div>

        {/* Right Sidebar (4 cols): DISPATCHES & STANCE BRIEFS (stories.slice(1, 4)) */}
        <aside className="lg:col-span-4 border-t-2 lg:border-t-0 lg:border-l border-[#D5CEC2] lg:pl-6 pt-6 lg:pt-0 space-y-6">
          <div className="border-b-2 border-[#262624] pb-1">
            <h3 className="text-xs font-ticker font-bold uppercase tracking-[0.2em] text-[#1C1A17] flex items-center gap-1.5">
              <Bookmark className="w-3.5 h-3.5 text-[#1C1A17]" />
              <span>DISPATCHES & STANCE BRIEFS</span>
            </h3>
          </div>

          <div className="space-y-6 divide-y divide-[#D5CEC2]">
            {sidebarStories.map((story) => (
              <article key={story.id} className="pt-5 first:pt-0">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[9px] font-ticker font-bold uppercase tracking-wider px-1.5 py-0.5 bg-[#EFECE4] text-[#1C1A17] border border-[#D5CEC2]">
                    {story.category}
                  </span>
                  {renderStancePill(story.stance)}
                  <span className="text-[#78716C] ml-auto font-ticker text-[10px]">
                    {formatTeletypeTime(story.timestamp)}
                  </span>
                </div>

                <h4 className="text-lg sm:text-xl font-bold font-headline text-[#1C1A17] leading-snug mb-2 hover:text-[#333]">
                  {story.sources?.[0]?.url ? (
                    <a href={story.sources[0].url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      {story.headline}
                    </a>
                  ) : (
                    story.headline
                  )}
                </h4>

                {story.imageUrl && (
                  <img
                    src={story.imageUrl}
                    alt=""
                    className="w-16 h-16 object-cover grayscale contrast-125 sepia-[0.15] float-right ml-3 mb-2 border border-stone-400 p-0.5"
                    onError={(e) => { e.currentTarget.style.display = 'none'; }}
                  />
                )}

                <p className="text-[#383531] text-xs sm:text-sm font-editorial-body leading-relaxed mb-3 text-justify">
                  {story.summary}
                </p>

                {/* Source Badge Footer */}
                <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-[#D5CEC2]">
                  {story.sources?.map((s, i) => renderSourceBadge(s, i))}
                </div>
              </article>
            ))}
          </div>

          {/* Editorial Transparency Seal */}
          <div className="p-3 bg-[#EFECE4]/80 border border-[#D5CEC2] text-[11px] text-[#57524D] font-editorial-body leading-relaxed">
            <h5 className="font-bold text-[#1C1A17] uppercase font-ticker tracking-wider text-[10px] mb-1">
              Press Bureau Policy
            </h5>
            <p className="italic">
              Noise filtration, multi-source deduplication, and viewpoint preservation applied in real time.
            </p>
          </div>
        </aside>

      </div>

      {/* SECTION 2: SECOND SECTION & DEVELOPMENTS (stories.slice(4)) */}
      {secondaryStories.length > 0 && (
        <section className="pt-8">
          <div className="border-b-2 border-[#262624] pb-1.5 mb-6 flex items-center justify-between">
            <h3 className="text-xs font-ticker font-bold uppercase tracking-[0.25em] text-[#1C1A17]">
              SECTION B: DEVELOPMENTS, SCIENCE & OPINION
            </h3>
            <span className="text-[11px] font-editorial-body italic text-[#666059]">
              ✦ Additional Telegraph Reports ✦
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 divide-y md:divide-y-0 md:divide-x divide-[#D5CEC2]">
            {secondaryStories.map((story, idx) => (
              <article key={story.id} className={`${idx > 0 ? 'md:pl-6' : ''} pt-6 md:pt-0 flex flex-col justify-between`}>
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[9px] font-ticker font-bold uppercase tracking-wider px-1.5 py-0.5 bg-[#EFECE4] text-[#1C1A17] border border-[#D5CEC2]">
                      {story.category}
                    </span>
                    <span>•</span>
                    {renderStancePill(story.stance)}
                  </div>

                  <h4 className="text-xl font-bold font-headline text-[#1C1A17] leading-snug mb-2.5 hover:text-[#333]">
                    {story.sources?.[0]?.url ? (
                      <a href={story.sources[0].url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                        {story.headline}
                      </a>
                    ) : (
                      story.headline
                    )}
                  </h4>

                  <p className="text-[#383531] text-sm font-editorial-body leading-relaxed mb-4 text-justify">
                    {story.summary}
                  </p>
                </div>

                {/* Source Badge Footer */}
                <div className="pt-3 border-t border-[#D5CEC2] flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {story.sources?.map((s, i) => renderSourceBadge(s, i))}
                  </div>
                  <span className="text-[10px] font-ticker text-[#78716C]">
                    {formatTeletypeTime(story.timestamp)}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

    </main>
  );
}

