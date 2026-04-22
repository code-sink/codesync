import { useState, useEffect } from 'react';

export function useActiveViewers(fileId) {
  const [activeUsers, setActiveUsers] = useState([]);

  useEffect(() => {
    if (!fileId) return;

    const mockUsers = [
      { id: '1', name: 'Alex', color: 'bg-blue-500', initials: 'A' },
      { id: '2', name: 'Sam', color: 'bg-emerald-500', initials: 'S' },
      { id: '3', name: 'Taylor', color: 'bg-purple-500', initials: 'T' },
      { id: '4', name: 'Jordan', color: 'bg-amber-500', initials: 'J' },
    ];

    // Simulate network delay
    const timer = setTimeout(() => {
      setActiveUsers(mockUsers);
    }, 500);

    return () => {
      clearTimeout(timer);
      // TODO: ws.close() or send "leave" event
    };
  }, [fileId]);

  return activeUsers;
}