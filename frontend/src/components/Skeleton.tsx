import React from "react";

export const Skeleton: React.FC<{ className?: string }> = ({ className = "" }) => {
  return (
    <div
      className={`animate-pulse bg-slate-800/60 rounded-lg dark:bg-slate-800/60 light:bg-slate-200 ${className}`}
    />
  );
};

export const MessageSkeleton: React.FC = () => {
  return (
    <div className="space-y-4 py-4">
      {/* Assistant bubble skeleton */}
      <div className="flex items-start space-x-3">
        <Skeleton className="w-8 h-8 rounded-xl shrink-0" />
        <div className="space-y-2 max-w-md w-full">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </div>
      {/* User bubble skeleton */}
      <div className="flex justify-end">
        <div className="space-y-2 max-w-xs w-full">
          <Skeleton className="h-4 w-full rounded-2xl" />
        </div>
      </div>
    </div>
  );
};

export const ConversationListSkeleton: React.FC = () => {
  return (
    <div className="space-y-2 p-2">
      {[1, 2, 3, 4].map((i) => (
        <Skeleton key={i} className="h-10 w-full rounded-xl" />
      ))}
    </div>
  );
};

export const CardSkeleton: React.FC<{ count?: number }> = ({ count = 3 }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-5 rounded-2xl border border-slate-800 bg-slate-900/40 space-y-3">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </div>
  );
};
