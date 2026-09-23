import React, { useState, useEffect } from 'react';
import { Calendar, Archive, FileText, CheckCircle2 } from 'lucide-react';

export default function ArchiveBar({
  archives = [],
  selectedDate,
  onSelectDate,
  selectedEditionId,
  onSelectEdition,
  isLoading,
  editionDateString
}) {
  // Format local YYYY-MM-DD
  const getLocalToday = () => {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const [vaultDate, setVaultDate] = useState(selectedDate || editionDateString || getLocalToday());

  useEffect(() => {
    if (selectedDate) {
      setVaultDate(selectedDate);
    } else if (editionDateString) {
      setVaultDate(editionDateString);
    }
  }, [selectedDate, editionDateString]);

  const handleDateChange = (newDate) => {
    if (newDate) {
      setVaultDate(newDate);
      onSelectDate(newDate);
    }
  };

  const formatDisplayDate = (dStr) => {
    if (!dStr) return '';
    try {
      const [y, m, d] = dStr.split('-');
      const dateObj = new Date(Number(y), Number(m) - 1, Number(d));
      return dateObj.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
    } catch (e) {
      return dStr;
    }
  };

  const activeVaultDate = vaultDate || selectedDate || getLocalToday();
  const currentDateArchive = archives.find((a) => a.date === activeVaultDate);
  const editionsForDate = currentDateArchive ? currentDateArchive.editions : [];
  const count = editionsForDate.length;
  const formattedDate = formatDisplayDate(activeVaultDate);
  const todayString = getLocalToday();

  return (
    <div className="border-t-2 border-b border-[#262624] py-2.5 my-3 bg-[#EFECE4]/60 text-[#1C1A17] font-serif">
      <div className="max-w-6xl mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-3 text-xs">
        
        {/* Left: Antique Calendar Pill & Date Input */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="inline-flex items-center gap-2 bg-[#F8F5EE] border border-[#262624] px-3 py-1 shadow-[2px_2px_0px_#262624]">
            <Calendar className="w-3.5 h-3.5 text-[#1C1A17] shrink-0" />
            <span className="font-ticker uppercase tracking-widest text-[10px] font-bold text-[#57524D]">
              DISPATCH VAULT:
            </span>
            <input
              type="date"
              value={vaultDate || todayString}
              max={todayString}
              disabled={isLoading}
              onChange={(e) => {
                e.preventDefault();
                handleDateChange(e.target.value);
              }}
              className="border-b border-[#262624] bg-transparent text-[#1C1A17] text-xs px-1 py-0.5 font-ticker rounded-none cursor-pointer focus:outline-none focus:bg-[#EFECE4]"
            />
          </div>

          {count > 0 && (
            <span className="font-ticker text-[10px] uppercase tracking-wider bg-[#262624] text-[#F8F5EE] px-2 py-0.5 font-semibold">
              {count} {count === 1 ? 'ISSUE ARCHIVED' : 'ISSUES ARCHIVED'}
            </span>
          )}
        </div>

        {/* Right: Editorial Archive Drawer Dropdown */}
        <div className="flex items-center gap-3 flex-wrap">
          {count > 0 ? (
            <div className="flex items-center gap-2">
              <span className="font-editorial-body italic text-[#44403C] text-xs hidden sm:inline">
                Curated Record for {formattedDate}:
              </span>
              <div className="relative inline-block">
                <select
                  value={selectedEditionId || ''}
                  disabled={isLoading}
                  onChange={(e) => {
                    e.preventDefault();
                    onSelectEdition(e.target.value);
                  }}
                  className="appearance-none bg-[#1C1A17] text-[#F8F5EE] text-xs font-serif pl-3 pr-8 py-1.5 border border-[#262624] cursor-pointer outline-none hover:bg-[#333] shadow-[2px_2px_0px_rgba(0,0,0,0.15)] font-bold tracking-wide"
                >
                  {editionsForDate.map((ed) => (
                    <option key={ed._id} value={ed._id}>
                      📜 Issue Selector: Edition #{ed.editionNumber} (Morning Final —{' '}
                      {new Date(ed.createdAt).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                      )
                    </option>
                  ))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-[#F8F5EE]">
                  <span className="text-[10px]">▼</span>
                </div>
              </div>
            </div>
          ) : (
            <span className="font-editorial-body italic text-[#78716C] text-xs flex items-center gap-1.5">
              <Archive className="w-3.5 h-3.5 opacity-60" />
              <span>No press editions recorded on {formattedDate}.</span>
            </span>
          )}
        </div>

      </div>
    </div>
  );
}

