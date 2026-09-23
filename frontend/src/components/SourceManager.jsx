import React, { useState, useEffect } from 'react';
import { X, Plus, Trash2, Video, FileText, Mail, Sparkles, Check, Radio } from 'lucide-react';

const QUICK_SEED_OUTLETS = [
  { name: "The Hindu", type: "BLOG" },
  { name: "Times of India", type: "BLOG" },
  { name: "Daily Thanthi", type: "NEWSLETTER" },
  { name: "The Verge", type: "BLOG" },
  { name: "MKBHD", type: "YOUTUBE" },
  { name: "madan gowri", type: "YOUTUBE" }
];

export default function SourceManager({ isOpen, onClose, token, sources = [], onUpdateSources }) {
  const [followedSources, setFollowedSources] = useState(sources || []);
  const [inputName, setInputName] = useState('');
  const [selectedType, setSelectedType] = useState('YOUTUBE (Video)');
  const [isLoading, setIsLoading] = useState(false);

  // Sync internal state if parent sources changes
  useEffect(() => {
    if (sources) {
      setFollowedSources(sources);
    }
  }, [sources]);

  // Fetch from MongoDB on Mount / Open
  useEffect(() => {
    const loadUserSources = async () => {
      const authToken = token || JSON.parse(localStorage.getItem('feedtoread_user') || '{}')?.token;
      if (!authToken) return;

      try {
        const res = await fetch(`http://${window.location.hostname}:8000/api/sources`, {
          headers: { 'Authorization': `Bearer ${authToken}` }
        });
        const data = await res.json();
        if (data.sources) {
          setFollowedSources(data.sources);
          onUpdateSources?.(data.sources);
        } else if (Array.isArray(data)) {
          setFollowedSources(data);
          onUpdateSources?.(data);
        }
      } catch (err) {
        console.error('Failed to load user wire sources:', err);
      }
    };

    if (isOpen) {
      loadUserSources();
    }
  }, [isOpen, token]);

  if (!isOpen) return null;

  // Handle "ADD SOURCE" Submission
  const handleAddSource = async (e) => {
    e.preventDefault();
    const trimmed = inputName.trim();
    if (!trimmed) return;

    setIsLoading(true);
    try {
      const authToken = token || JSON.parse(localStorage.getItem('feedtoread_user') || '{}')?.token;
      let cleanType = selectedType.toUpperCase();
      if (cleanType.includes('YOUTUBE')) cleanType = 'YOUTUBE';
      else if (cleanType.includes('BLOG')) cleanType = 'BLOG';
      else if (cleanType.includes('NEWSLETTER')) cleanType = 'NEWSLETTER';
      else if (cleanType.includes('RSS')) cleanType = 'RSS';

      if (authToken) {
        const res = await fetch(`http://${window.location.hostname}:8000/api/sources`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${authToken}`
          },
          body: JSON.stringify({
            sourceName: trimmed,
            sourceType: cleanType
          })
        });

        const data = await res.json();
        if (data.source) {
          setFollowedSources(prev => {
            const updated = [data.source, ...prev.filter(s => (s._id || s.id) !== (data.source._id || data.source.id))];
            onUpdateSources?.(updated);
            return updated;
          });
          setInputName('');
        }
      } else {
        // Fallback for offline/guest
        const newSource = {
          _id: `src_${Date.now()}`,
          sourceName: trimmed,
          sourceType: cleanType,
          isActive: true
        };
        setFollowedSources(prev => {
          const updated = [newSource, ...prev.filter(s => (s.sourceName || s.name || '').toLowerCase() !== trimmed.toLowerCase())];
          onUpdateSources?.(updated);
          return updated;
        });
        setInputName('');
      }
    } catch (err) {
      console.error('Error adding source:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Quick-Seed Pills Handler
  const handleQuickSeed = async (outlet) => {
    const authToken = token || JSON.parse(localStorage.getItem('feedtoread_user') || '{}')?.token;
    setIsLoading(true);
    try {
      if (authToken) {
        const res = await fetch(`http://${window.location.hostname}:8000/api/sources`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${authToken}`
          },
          body: JSON.stringify({
            sourceName: outlet.name,
            sourceType: outlet.type
          })
        });

        const data = await res.json();
        if (data.source) {
          setFollowedSources(prev => {
            const updated = [data.source, ...prev.filter(s => (s._id || s.id) !== (data.source._id || data.source.id))];
            onUpdateSources?.(updated);
            return updated;
          });
        }
      } else {
        const newSource = {
          _id: `src_${Date.now()}`,
          sourceName: outlet.name,
          sourceType: outlet.type,
          isActive: true
        };
        setFollowedSources(prev => {
          const updated = [newSource, ...prev.filter(s => (s.sourceName || s.name || '').toLowerCase() !== outlet.name.toLowerCase())];
          onUpdateSources?.(updated);
          return updated;
        });
      }
    } catch (err) {
      console.error('Failed to quick-seed source:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Toggle Active/Inactive
  const handleToggleSource = async (id) => {
    const authToken = token || JSON.parse(localStorage.getItem('feedtoread_user') || '{}')?.token;
    if (authToken && !String(id).startsWith('src_')) {
      try {
        const res = await fetch(`http://${window.location.hostname}:8000/api/sources/${id}/toggle`, {
          method: 'PATCH',
          headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.ok) {
          const data = await res.json();
          setFollowedSources(prev => {
            const updated = prev.map(s => (s._id || s.id) === id ? { ...s, isActive: data.source?.isActive ?? !s.isActive } : s);
            onUpdateSources?.(updated);
            return updated;
          });
          return;
        }
      } catch (err) {
        console.error('Failed to toggle source on backend:', err);
      }
    }

    setFollowedSources(prev => {
      const updated = prev.map(s => (s._id || s.id) === id ? { ...s, isActive: s.isActive !== false ? false : true } : s);
      onUpdateSources?.(updated);
      return updated;
    });
  };

  // Handle Remove / Delete
  const handleDeleteSource = async (id) => {
    const authToken = token || JSON.parse(localStorage.getItem('feedtoread_user') || '{}')?.token;
    if (authToken && !String(id).startsWith('src_')) {
      try {
        await fetch(`http://${window.location.hostname}:8000/api/sources/${id}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${authToken}` }
        });
      } catch (err) {
        console.error('Failed to delete source:', err);
      }
    }

    setFollowedSources(prev => {
      const updated = prev.filter(s => (s._id || s.id) !== id);
      onUpdateSources?.(updated);
      return updated;
    });
  };

  const getTypeIcon = (type) => {
    switch (type) {
      case 'YOUTUBE':
        return <Video className="w-4 h-4 text-red-600 shrink-0" />;
      case 'NEWSLETTER':
        return <Mail className="w-4 h-4 text-amber-700 shrink-0" />;
      case 'RSS':
        return <Radio className="w-4 h-4 text-orange-600 shrink-0" />;
      case 'BLOG':
      default:
        return <FileText className="w-4 h-4 text-emerald-700 shrink-0" />;
    }
  };

  const activeCount = followedSources.filter(s => s.isActive !== false).length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/60 backdrop-blur-xs p-4">
      <div className="bg-[#FBF8F1] border-4 border-double border-stone-900 shadow-2xl max-w-lg w-full p-6 sm:p-8 relative font-sans-ui text-stone-900 max-h-[90vh] flex flex-col">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b-2 border-stone-900 pb-4 mb-4">
          <div>
            <span className="block text-xs uppercase tracking-widest text-stone-600 font-serif font-bold">
              Dispatch Wire Manager
            </span>
            <h2 className="text-xl sm:text-2xl font-serif font-bold tracking-tight text-stone-900 uppercase">
              Curate Your Editorial Sources
            </h2>
          </div>
          <button 
            onClick={onClose}
            className="text-stone-500 hover:text-stone-900 p-1 border border-stone-300 hover:border-stone-900 transition-colors cursor-pointer"
            aria-label="Close Source Manager"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto space-y-6 pr-1">
          {/* Quick-Seed Pills Section */}
          <div>
            <label className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-stone-700 mb-2 font-serif">
              <Sparkles className="w-3.5 h-3.5 text-amber-600" />
              Quick-Seed Wire Outlets (Click to Follow)
            </label>
            <div className="flex flex-wrap gap-2">
              {QUICK_SEED_OUTLETS.map((outlet) => {
                const existing = followedSources.find(s => (s.sourceName || s.name || '').toLowerCase() === outlet.name.toLowerCase());
                const isFollowedAndActive = existing && existing.isActive !== false;

                return (
                  <button
                    key={outlet.name}
                    type="button"
                    onClick={() => handleQuickSeed(outlet)}
                    disabled={isLoading}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border transition-all cursor-pointer ${
                      isFollowedAndActive
                        ? "bg-stone-200 border-stone-300 text-stone-700"
                        : "bg-stone-100 hover:bg-stone-900 hover:text-[#FBF8F1] border-stone-400 text-stone-800"
                    }`}
                  >
                    {getTypeIcon(outlet.type)}
                    <span>{outlet.name}</span>
                    {isFollowedAndActive ? (
                      <span className="text-[10px] uppercase font-bold text-emerald-800">✓ Active</span>
                    ) : (
                      <Plus className="w-3 h-3 text-stone-500" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Custom Source Input */}
          <form onSubmit={handleAddSource} className="border-t border-stone-300 pt-4">
            <label className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-2 font-serif">
              Add Publication or Desk by Name
            </label>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                placeholder="e.g. madan gowri, MKBHD, The Hindu..."
                value={inputName}
                onChange={(e) => setInputName(e.target.value)}
                className="flex-1 px-3 py-2 bg-[#FBF8F1] border border-stone-400 focus:border-stone-900 outline-none text-stone-900 text-sm"
              />
              <div className="flex gap-2">
                <select
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value)}
                  className="px-2 py-2 bg-[#FBF8F1] border border-stone-400 focus:border-stone-900 outline-none text-stone-900 text-xs font-semibold cursor-pointer"
                >
                  <option value="YOUTUBE (Video)">YOUTUBE (Video)</option>
                  <option value="NEWSLETTER (Digest)">NEWSLETTER (Digest)</option>
                  <option value="BLOG (Article)">BLOG (Article)</option>
                  <option value="RSS (Feed)">RSS (Feed)</option>
                </select>
                <button
                  type="submit"
                  disabled={isLoading || !inputName.trim()}
                  className="bg-stone-900 hover:bg-stone-800 disabled:opacity-50 text-[#FBF8F1] px-4 py-2 text-xs font-bold uppercase tracking-wider font-serif transition-colors shrink-0 cursor-pointer"
                >
                  {isLoading ? 'Adding...' : 'Add Source'}
                </button>
              </div>
            </div>
          </form>

          {/* Followed Sources List */}
          <div className="border-t border-stone-300 pt-4">
            <div className="flex justify-between items-center mb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-stone-700 font-serif">
                Followed Wire Sources ({activeCount} Active / {followedSources.length} Total)
              </span>
              <span className="text-[11px] italic text-stone-500 font-serif">Persisted in MongoDB</span>
            </div>

            {followedSources.length === 0 ? (
              <div className="text-center py-6 border border-dashed border-stone-300 bg-stone-50 text-stone-500 text-xs italic font-serif">
                No wire sources followed. Click quick-seed pills above or add a publication to build your personalized wire.
              </div>
            ) : (
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {followedSources.map((source) => {
                  const sId = source._id || source.id;
                  const sName = source.sourceName || source.name;
                  const sType = source.sourceType || source.type || 'BLOG';
                  const isActive = source.isActive !== false;

                  return (
                    <div
                      key={sId}
                      className={`flex items-center justify-between p-2.5 border transition-colors ${
                        isActive
                          ? "bg-stone-100 border-stone-300 hover:border-stone-400"
                          : "bg-stone-100/50 border-stone-200 opacity-60"
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {/* Toggle Active Checkbox */}
                        <button
                          type="button"
                          onClick={() => handleToggleSource(sId)}
                          className={`w-4 h-4 rounded-sm border flex items-center justify-center transition-colors cursor-pointer shrink-0 ${
                            isActive
                              ? "bg-stone-900 border-stone-900 text-white"
                              : "border-stone-400 bg-white hover:border-stone-600"
                          }`}
                          title={isActive ? "Deactivate source (hide stories)" : "Activate source (show stories)"}
                          aria-label={`Toggle active state for ${sName}`}
                        >
                          {isActive && <Check className="w-3 h-3 stroke-[3]" />}
                        </button>

                        <div className="flex items-center gap-2 min-w-0">
                          {getTypeIcon(sType)}
                          <span className={`font-semibold text-sm truncate ${isActive ? "text-stone-900" : "text-stone-500 line-through"}`}>
                            {sName}
                          </span>
                          <span className="text-[9px] px-1.5 py-0.5 bg-stone-200 border border-stone-300 text-stone-600 font-bold uppercase shrink-0">
                            {sType}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {!isActive && (
                          <span className="text-[10px] uppercase font-mono tracking-tight text-amber-900 bg-amber-50 border border-amber-200 px-1 py-0.5">
                            Paused
                          </span>
                        )}
                        <button
                          onClick={() => handleDeleteSource(sId)}
                          className="text-stone-400 hover:text-red-700 p-1 transition-colors cursor-pointer"
                          title="Remove source"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Footer info & Done Curating action */}
        <div className="mt-4 pt-3 border-t border-stone-300 flex items-center justify-between">
          <span className="text-[11px] font-mono text-stone-500">
            {activeCount} feeds active
          </span>
          <button
            onClick={onClose}
            className="px-5 py-2 bg-stone-900 text-[#FBF8F1] text-xs font-bold uppercase font-serif hover:bg-stone-800 transition-colors cursor-pointer"
          >
            Done Curating
          </button>
        </div>
      </div>
    </div>
  );
}
