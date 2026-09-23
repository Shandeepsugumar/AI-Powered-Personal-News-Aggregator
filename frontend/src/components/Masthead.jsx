import React from 'react';
import { RefreshCw, SlidersHorizontal, LogIn, LogOut, UserCheck, ShieldAlert, Newspaper, Radio } from 'lucide-react';

const CATEGORIES = ["ALL", "TECHNOLOGY", "OPINION", "SCIENCE", "BUSINESS"];

export default function Masthead({
  user,
  onOpenAuth,
  onSignOut,
  onOpenSources,
  onRefreshEdition,
  isLoading,
  activeCategory,
  onSelectCategory,
  sourcesCount,
  activeEditionNumber = 1,
  activeDateString
}) {
  const todayFormatted = activeDateString
    ? new Date(activeDateString + 'T00:00:00').toLocaleDateString('en-US', {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
        year: 'numeric'
      })
    : new Date().toLocaleDateString('en-US', {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
        year: 'numeric'
      });

  return (
    <header className="border-b-4 border-[#262624] select-none text-[#1C1A17]">
      
      {/* Fine double hairline rule at top */}
      <div className="border-t-2 border-b border-[#262624] py-0.5 bg-[#F8F5EE]"></div>

      {/* Logged Out / Guest Banner */}
      {!user && (
        <div className="bg-[#FAF3DC] border-b border-[#D5CEC2] px-4 py-1.5 text-xs font-editorial-body text-[#4D3800] flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-amber-800 shrink-0" />
            <span>
              <strong>Guest Pressroom Pass</strong> · Authenticate your personal credential to unlock custom wire curation & multi-edition archives.
            </span>
          </div>
          <button
            onClick={onOpenAuth}
            className="font-bold underline uppercase tracking-wider text-[11px] hover:text-[#1C1A17] cursor-pointer font-ticker"
          >
            Claim Pass / Sign In →
          </button>
        </div>
      )}

      {/* Top Utility Rail */}
      <div className="border-b border-[#D5CEC2] px-4 sm:px-6 py-2 text-xs flex flex-wrap justify-between items-center gap-3 bg-[#F8F5EE]/95">
        
        {/* Left: Vol & Vintage Ink Stamp */}
        <div className="flex items-center gap-3">
          <span className="font-ticker font-bold tracking-widest text-[#57524D] text-[11px]">
            VOL. I · NO. 42
          </span>
          <span className="border border-stone-800 px-2 py-0.5 uppercase tracking-widest text-[11px] font-mono font-bold bg-amber-50/50 shadow-[1px_1px_0px_#262624] text-[#1C1A17]">
            EDITION #{activeEditionNumber} (MORNING FINAL)
          </span>
        </div>

        {/* Center: Full publication date with ornamental dingbat */}
        <div className="font-editorial-body italic text-sm text-[#1C1A17] font-medium tracking-wide">
          <span>✦ {todayFormatted} ✦</span>
        </div>

        {/* Right: Minimalist user badge with authentic press pass icon */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-ticker text-[11px] text-[#57524D]">
            <Radio className="w-3.5 h-3.5 text-emerald-800" />
            <span>WIRE SOURCES ({sourcesCount})</span>
          </div>

          <span className="text-[#D5CEC2]">|</span>

          {user ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-xs bg-[#EFECE4] px-2 py-0.5 border border-[#D5CEC2]">
                <Newspaper className="w-3 h-3 text-[#1C1A17]" />
                <span className="font-semibold text-[#1C1A17] font-ticker text-[11px]">{user.name}</span>
              </div>
              <button
                onClick={onSignOut}
                className="font-ticker text-[11px] uppercase tracking-wider text-[#57524D] hover:text-[#1C1A17] hover:underline cursor-pointer"
                title="Sign Out"
              >
                [Sign Out]
              </button>
            </div>
          ) : (
            <button
              onClick={onOpenAuth}
              className="font-ticker text-[11px] font-bold uppercase tracking-wider bg-[#1C1A17] text-[#F8F5EE] px-2.5 py-1 hover:bg-[#333] transition-colors cursor-pointer"
            >
              Sign In
            </button>
          )}
        </div>
      </div>

      {/* Main Header */}
      <div className="pt-7 pb-6 text-center px-4 border-b border-[#262624] relative bg-[#F8F5EE]">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-center gap-3 text-[#57524D] text-[11px] font-ticker uppercase tracking-[0.3em] mb-2">
            <span>THE NATIONAL AI BROADSHEET</span>
            <span>•</span>
            <span>PUBLISHED CONTINUOUSLY IN NEW YORK</span>
          </div>

          <h1 className="text-5xl sm:text-7xl md:text-8xl font-masthead font-black tracking-tight text-[#1C1A17] uppercase my-2 drop-shadow-[0_2px_1px_rgba(0,0,0,0.15)] leading-none select-none">
            THE DAILY BRIEF
          </h1>

          <p className="font-editorial-body italic text-sm sm:text-base text-[#44403C] font-normal max-w-2xl mx-auto pt-1">
            "Synthesized AI Dispatches · YouTube Channels, Curated Newsletters & Wire Bureaus"
          </p>
        </div>

        {/* Integrated Action Toolbar */}
        <div className="mt-5 flex flex-wrap justify-center items-center gap-3">
          <button
            onClick={onRefreshEdition}
            disabled={isLoading}
            className="bg-[#1C1A17] text-[#F8F5EE] hover:bg-[#333] border border-stone-900 uppercase tracking-widest text-xs font-serif font-bold px-4 py-2 shadow-sm active:translate-y-0.5 transition-transform flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{isLoading ? "Presses Running..." : "✦ Print New Edition"}</span>
          </button>

          <button
            onClick={onOpenSources}
            className="border-2 border-stone-900 bg-transparent text-stone-900 hover:bg-stone-200 uppercase tracking-widest text-xs font-serif font-bold px-4 py-2 cursor-pointer flex items-center gap-2 transition-colors"
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-[#1C1A17]" />
            <span>Manage Wire ({sourcesCount})</span>
          </button>
        </div>
      </div>

      {/* Category Navigation Bar */}
      <nav className="bg-[#EFECE4]/70 px-4 flex justify-center border-b border-[#262624] overflow-x-auto scrollbar-none">
        <div className="flex space-x-1 sm:space-x-6 py-1.5">
          {CATEGORIES.map((category) => {
            const isActive = activeCategory === category;
            return (
              <button
                key={category}
                onClick={() => onSelectCategory(category)}
                className={`px-3 py-1 text-xs font-headline font-bold tracking-[0.18em] uppercase transition-all whitespace-nowrap cursor-pointer border-b-2 ${
                  isActive
                    ? "border-[#1C1A17] text-[#1C1A17] bg-[#F8F5EE]"
                    : "border-transparent text-[#666059] hover:text-[#1C1A17] hover:bg-[#F8F5EE]/50"
                }`}
              >
                {category}
              </button>
            );
          })}
        </div>
      </nav>
    </header>
  );
}

