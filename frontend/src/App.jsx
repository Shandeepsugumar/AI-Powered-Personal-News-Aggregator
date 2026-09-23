import React, { useState, useEffect } from 'react';
import Masthead from './components/Masthead';
import NewspaperView from './components/NewspaperView';
import AuthModal from './components/AuthModal';
import SourceManager from './components/SourceManager';
import ArchiveBar from './components/ArchiveBar';
import { Clock, AlertCircle } from 'lucide-react';

function getLocalDateString(d = new Date()) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}


export default function App() {
  const [user, setUser] = useState(null);
  const [followedSources, setFollowedSources] = useState([]);
  const [edition, setEdition] = useState([]);
  const [activeCategory, setActiveCategory] = useState('ALL');
  const [isLoading, setIsLoading] = useState(false);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [isSourcesOpen, setIsSourcesOpen] = useState(false);

  // Multi-Edition & Archive state
  const [activeEditionNumber, setActiveEditionNumber] = useState(1);
  const [activeDateString, setActiveDateString] = useState(getLocalDateString());
  const [activeEditionId, setActiveEditionId] = useState(null);
  const [archives, setArchives] = useState([]);
  const [cooldownNotice, setCooldownNotice] = useState(null);

  const fetchArchivesList = async (token) => {
    if (!token) return;
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/newspaper/archives`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setArchives(data);
      }
    } catch (err) {
      console.error('Failed to load archives:', err);
    }
  };

  const loadUserNewspaperAndArchives = async (token) => {
    if (!token) return;
    setIsLoading(true);
    try {
      // 1. Fetch latest edition (creates Edition #1 automatically if none today)
      const res = await fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/newspaper/latest`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const edData = await res.json();
        if (edData?.stories && Array.isArray(edData.stories)) {
          setEdition(edData.stories);
          setActiveEditionNumber(edData.editionNumber || 1);
          setActiveDateString(edData.dateString || getLocalDateString());
          setActiveEditionId(edData._id);
        } else {
          setEdition([]);
        }
      }
      // 2. Fetch archives list
      await fetchArchivesList(token);
    } catch (err) {
      console.error('Failed to load live newspaper from backend:', err);
      setEdition([]);
    } finally {
      setIsLoading(false);
    }
  };

  // Initial Hydration resilience policy: direct browser storage or fallback
  useEffect(() => {
    // 1. User Session
    const storedUser = localStorage.getItem('feedtoread_user');
    let parsedUser = null;
    if (storedUser) {
      try {
        parsedUser = JSON.parse(storedUser);
        setUser(parsedUser);
      } catch (e) {
        console.error('Failed to parse user from localStorage', e);
      }
    }

    // 2. Followed Sources (From Backend if logged in, else LocalStorage)
    if (parsedUser?.token) {
      fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/sources`, {
        headers: { 'Authorization': `Bearer ${parsedUser.token}` }
      })
        .then(res => res.json())
        .then(data => {
          const list = data.sources || (Array.isArray(data) ? data : []);
          const normalized = list.map(s => ({
            id: s._id || s.id,
            _id: s._id || s.id,
            name: s.sourceName || s.name,
            sourceName: s.sourceName || s.name,
            type: s.sourceType || s.type || 'BLOG',
            sourceType: s.sourceType || s.type || 'BLOG',
            isActive: s.isActive !== undefined ? s.isActive : true
          }));
          setFollowedSources(normalized);
          localStorage.setItem('followed_sources', JSON.stringify(normalized));
        })
        .catch(err => {
          console.error('Failed to fetch backend sources on mount:', err);
          setFollowedSources([]);
        });

      // 3. Load latest edition & archive list from backend
      loadUserNewspaperAndArchives(parsedUser.token);
    } else {
      const storedSources = localStorage.getItem('followed_sources');
      if (storedSources) {
        try {
          const parsed = JSON.parse(storedSources);
          setFollowedSources(Array.isArray(parsed) ? parsed : []);
        } catch {
          setFollowedSources([]);
        }
      } else {
        setFollowedSources([]);
      }

      // Guest mode - no hardcoded mock stories
      setEdition([]);
    }
  }, []);

  // Handlers
  const handleAuthSuccess = (userData) => {
    setUser(userData);
    if (userData?.token) {
      // 1. Fetch sources from MongoDB
      fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/sources`, {
        headers: { 'Authorization': `Bearer ${userData.token}` }
      })
        .then(res => res.json())
        .then(data => {
          const list = data.sources || (Array.isArray(data) ? data : []);
          const normalized = list.map(s => ({
            id: s._id || s.id,
            _id: s._id || s.id,
            name: s.sourceName || s.name,
            sourceName: s.sourceName || s.name,
            type: s.sourceType || s.type || 'BLOG',
            sourceType: s.sourceType || s.type || 'BLOG',
            isActive: s.isActive !== undefined ? s.isActive : true
          }));
          setFollowedSources(normalized);
          localStorage.setItem('followed_sources', JSON.stringify(normalized));
        })
        .catch(err => console.error('Failed to load sources on auth success:', err));

      // 2. Fetch live newspaper edition + archives
      loadUserNewspaperAndArchives(userData.token);
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('feedtoread_user');
    localStorage.removeItem('followed_sources');
    setUser(null);
    setArchives([]);
    setActiveEditionNumber(1);
    setActiveDateString(getLocalDateString());
    setCooldownNotice(null);
    setEdition([]);
    setFollowedSources([]);
  };

  const handleUpdateSources = (newSources) => {
    setFollowedSources(newSources);
  };

  const handleRefreshEdition = async () => {
    setIsLoading(true);
    setCooldownNotice(null);

    // If user is authenticated, call backend POST /api/newspaper/refresh
    if (user?.token) {
      try {
        const response = await fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/newspaper/refresh`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${user.token}`
          }
        });

        const data = await response.json();

        if (response.ok) {
          if (data.isNew === false) {
            // No fresh dispatches / deduplication notice
            setCooldownNotice({
              message: data.message || "Presses waiting: No fresh dispatches since previous edition."
            });

            if (data.edition?.stories) {
              setEdition(data.edition.stories);
              setActiveEditionNumber(data.edition.editionNumber || 1);
              setActiveDateString(data.edition.dateString || getLocalDateString());
              setActiveEditionId(data.edition._id);
              localStorage.setItem('feedtoread_edition', JSON.stringify(data.edition.stories));
            }
          } else {
            // Fresh issue published
            setCooldownNotice(null);
            if (data.edition?.stories) {
              setEdition(data.edition.stories);
              setActiveEditionNumber(data.edition.editionNumber || 1);
              setActiveDateString(data.edition.dateString || getLocalDateString());
              setActiveEditionId(data.edition._id);
              localStorage.setItem('feedtoread_edition', JSON.stringify(data.edition.stories));
            }
            // Refresh archives list
            await fetchArchivesList(user.token);
          }
        } else {
          console.error('Failed to refresh edition:', data.error);
        }
      } catch (err) {
        console.error('Error refreshing edition:', err);
      } finally {
        setIsLoading(false);
      }
      return;
    }

    // Guest fallback - no hardcoded mock data
    setTimeout(() => {
      setEdition([]);
      setIsLoading(false);
    }, 500);
  };

  // Date and Historical Edition Selection Handlers
  const handleSelectArchiveDate = async (dateStr) => {
    if (!dateStr) return;

    // Convert DD/MM/YYYY to YYYY-MM-DD if sent in UK/Indian format
    let normalizedDate = dateStr;
    if (normalizedDate.includes('/')) {
      const parts = normalizedDate.split('/');
      if (parts[0].length === 2) {
        normalizedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
      }
    }

    setActiveDateString(normalizedDate);
    setCooldownNotice(null);

    // 1. First check in local cached archives list
    const dateArchive = archives.find(a => a.date === normalizedDate);
    if (dateArchive && dateArchive.editions.length > 0) {
      const firstEd = dateArchive.editions[0];
      handleSelectEdition(firstEd._id);
      return;
    }

    // 2. Query backend GET /api/newspaper/archive?date=...
    if (user?.token) {
      try {
        setIsLoading(true);
        const res = await fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/newspaper/archive?date=${encodeURIComponent(normalizedDate)}`, {
          headers: { 'Authorization': `Bearer ${user.token}` }
        });
        if (res.ok) {
          const data = await res.json();
          if (data?.editions && data.editions.length > 0) {
            handleSelectEdition(data.editions[0]._id);
            fetchArchivesList(user.token);
            return;
          }
        }
      } catch (err) {
        console.error('Failed to query archive by date:', err);
      } finally {
        setIsLoading(false);
      }
    }

    setActiveEditionId(null);
  };

  const handleSelectEdition = async (editionId) => {
    if (!user?.token || !editionId) return;
    setIsLoading(true);
    setCooldownNotice(null);

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/newspaper/edition/${editionId}`, {
        headers: { 'Authorization': `Bearer ${user.token}` }
      });
      if (res.ok) {
        const edData = await res.json();
        if (edData?.stories) {
          setEdition(edData.stories);
          setActiveEditionNumber(edData.editionNumber || 1);
          setActiveDateString(edData.dateString || getLocalDateString());
          setActiveEditionId(edData._id);
          localStorage.setItem('feedtoread_edition', JSON.stringify(edData.stories));
        }
      }
    } catch (err) {
      console.error('Failed to load historical edition:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Strict Wire Story Filtering
  const activeNames = followedSources
    .filter(s => s.isActive !== false)
    .map(s => (s.name || s.sourceName || '').trim().toLowerCase());

  const displayedStories = edition.filter(story => {
    if (activeNames.length === 0) return false; // Strict mode: show zero-state if no sources active
    return story.sources?.some(src => 
      activeNames.some(name => {
        const srcName = (src.name || '').toLowerCase();
        return srcName.includes(name) || name.includes(srcName);
      })
    );
  });

  return (
    <div className="min-h-screen bg-[#F8F5EE] text-[#1C1A17] font-editorial-body flex flex-col selection:bg-[#262624] selection:text-[#F8F5EE]">
      <div className="flex-1">
        <Masthead
          user={user}
          onOpenAuth={() => setIsAuthOpen(true)}
          onSignOut={handleSignOut}
          onOpenSources={() => setIsSourcesOpen(true)}
          onRefreshEdition={handleRefreshEdition}
          isLoading={isLoading}
          activeCategory={activeCategory}
          onSelectCategory={setActiveCategory}
          sourcesCount={followedSources.filter(s => s.isActive !== false).length}
          activeEditionNumber={activeEditionNumber}
          activeDateString={activeDateString}
        />

        {/* Date & Edition Archive Selector */}
        {user && (
          <ArchiveBar
            archives={archives}
            selectedDate={activeDateString}
            editionDateString={activeDateString}
            onSelectDate={handleSelectArchiveDate}
            selectedEditionId={activeEditionId}
            onSelectEdition={handleSelectEdition}
            isLoading={isLoading}
          />
        )}

        {/* Editorial Cooldown Teletype Notice */}
        {cooldownNotice && (
          <div className="max-w-5xl mx-auto px-4 my-3">
            <div className="border border-amber-800 bg-[#FDF6E2] text-amber-950 font-mono text-xs px-4 py-2.5 flex items-center justify-between shadow-[2px_2px_0px_#78350F]">
              <div className="flex items-center gap-2.5">
                <Clock className="w-4 h-4 text-amber-900 shrink-0 animate-pulse" />
                <span className="tracking-tight">
                  <strong className="uppercase">TELETYPE DISPATCH:</strong> {cooldownNotice.message || "Presses waiting: No fresh dispatches since previous edition."} (Displaying Edition #{activeEditionNumber}).
                </span>
              </div>
              <button
                onClick={() => setCooldownNotice(null)}
                className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 border border-amber-900 hover:bg-amber-200/80 cursor-pointer ml-3 shrink-0"
              >
                [ACKNOWLEDGE]
              </button>
            </div>
          </div>
        )}

        <NewspaperView
          stories={displayedStories}
          followedSources={followedSources}
          isLoading={isLoading}
          activeCategory={activeCategory}
          onResetCategory={() => setActiveCategory('ALL')}
          onOpenSources={() => setIsSourcesOpen(true)}
        />
      </div>

      {/* Broadsheet Footer Colophon */}
      <footer className="border-t-4 border-[#262624] bg-[#EFECE4] py-8 px-4 text-center font-editorial-body text-[#44403C] text-xs mt-auto">
        <div className="max-w-4xl mx-auto space-y-2">
          <div className="border-t border-b border-[#262624] py-1 mb-3">
            <span className="font-ticker uppercase tracking-[0.25em] text-[10px] text-[#1C1A17] font-bold">
              ✦ FEEDTOREAD EDITORIAL PRESS & SYNDICATION BUREAU · VOL. I ✦
            </span>
          </div>
          <p className="italic text-sm text-[#1C1A17]">
            Published with continuous automated scraping, audio transcription, noise filtering & stance preservation.
          </p>
          <p className="text-[11px] font-ticker text-[#78716C] pt-2 border-t border-[#D5CEC2]">
            © 2026 FeedToRead Systems Inc. All rights reserved. Self-contained local storage persistence & MongoDB Atlas synchronization enabled.
          </p>
        </div>
      </footer>

      {/* Modals & Drawers */}
      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        onAuthSuccess={handleAuthSuccess}
        user={user}
      />

      <SourceManager
        isOpen={isSourcesOpen}
        onClose={() => setIsSourcesOpen(false)}
        token={user?.token}
        sources={followedSources}
        onUpdateSources={handleUpdateSources}
      />
    </div>
  );
}
