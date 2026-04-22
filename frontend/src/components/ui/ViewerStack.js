import React, { useState } from 'react';

export function ViewerStack({ users }) {
  const [showDropdown, setShowDropdown] = useState(false);

  if (users.length <= 1) return null;
  
  const MAX_DISPLAY = 3;
  const displayUsers = users.slice(0, MAX_DISPLAY);
  const hiddenUsers = users.slice(MAX_DISPLAY);
  const extraCount = hiddenUsers.length;

  if (users.length === 0) return null;

  return (
    <div className="flex items-center space-x-4">
      <span style={{ fontSize: 13, fontWeight: 600, color: '#ededed', letterSpacing: '0.02em' }}>
        Live users
      </span>
      
      <div className="relative flex items-center">
        {/* Overlapping Avatars */}
        <div className="flex -space-x-2">
          {displayUsers.map((user) => (
            <div
              key={user.id}
              className={`group relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-xs font-bold text-white ring-2 ring-slate-900 transition-transform hover:z-10 hover:-translate-y-1 ${user.color}`}
            >
              {user.avatarUrl ? (
                <img 
                  src={user.avatarUrl} 
                  alt={user.name} 
                  className="h-full w-full rounded-full object-cover" 
                />
              ) : (
                user.initials
              )}
              
              {/* Hover Tooltip */}
              <div className="pointer-events-none absolute -bottom-10 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-purple-500/30 bg-slate-800 px-2.5 py-1 text-xs font-semibold text-purple-100 opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                {user.name}
              </div>
            </div>
          ))}
          
          {/* Interactive Overflow Badge */}
          {extraCount > 0 && (
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="relative z-0 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-purple-900/40 text-xs font-bold text-purple-200 ring-2 ring-slate-900 transition-colors hover:bg-purple-800/60 focus:outline-none"
            >
              +{extraCount}
            </button>
          )}
        </div>

        {/* Dropdown Menu for Hidden Users */}
        {showDropdown && extraCount > 0 && (
          <div className="absolute right-0 top-12 z-20 w-48 overflow-hidden rounded-md border border-purple-500/20 bg-slate-800 shadow-xl ring-1 ring-black/5">
            <div className="bg-slate-900/50 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Other Viewers
            </div>
            <div className="max-h-48 overflow-y-auto py-1">
              {hiddenUsers.map((user) => (
                <div 
                  key={user.id} 
                  className="flex items-center px-4 py-2 text-sm text-slate-200 transition-colors hover:bg-slate-700/50"
                >
                  <div className={`mr-3 flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold text-white ${user.color}`}>
                    {user.initials}
                  </div>
                  {user.name}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}