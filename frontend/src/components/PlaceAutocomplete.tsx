import { Loader2, MapPin } from 'lucide-react';
import { useId, useState, type KeyboardEvent, type ReactNode } from 'react';
import { useGeocode } from '../api/plan';
import { useDebouncedValue } from '../lib/useDebouncedValue';
import type { LonLat, Place } from '../types';

interface PlaceAutocompleteProps {
  label: string;
  placeholder: string;
  icon: ReactNode;
  value: Place | null;
  onChange: (place: Place | null) => void;
  /** Rank suggestions near this point (the map's centre), if set. */
  near: LonLat | null;
}

/** A combobox that searches places as you type (debounced) and supports full keyboard use. */
export function PlaceAutocomplete({
  label,
  placeholder,
  icon,
  value,
  onChange,
  near,
}: PlaceAutocompleteProps) {
  const id = useId();
  const listId = `${id}-list`;
  const [text, setText] = useState(value?.label ?? '');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [syncedLabel, setSyncedLabel] = useState(value?.label);

  // Keep the text in sync when the parent changes the value (e.g. swapping origin/destination).
  if (value?.label !== syncedLabel) {
    setSyncedLabel(value?.label);
    setText(value?.label ?? '');
  }

  const query = useDebouncedValue(text, 300);
  const searching = open && value === null && query.trim().length >= 2;
  const geocode = useGeocode(searching ? query : '', near);
  const results = searching ? (geocode.data ?? []) : [];
  const showList = searching && (results.length > 0 || !geocode.isFetching);

  function choose(place: Place) {
    onChange(place);
    setOpen(false);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!showList) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter' && results[active]) {
      event.preventDefault();
      choose(results[active]);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <div className="flex items-center gap-2.5 rounded-lg bg-surface px-3 ring-1 ring-line transition-shadow focus-within:ring-2 focus-within:ring-accent">
        <span className="shrink-0 text-muted">{icon}</span>
        <input
          id={id}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && results[active] ? `${listId}-${active}` : undefined}
          autoComplete="off"
          spellCheck={false}
          placeholder={placeholder}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setActive(0);
            setOpen(true);
            if (value) onChange(null);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onKeyDown={onKeyDown}
          className="h-11 min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted focus-visible:outline-none"
        />
        {searching && geocode.isFetching && (
          <Loader2 aria-hidden className="size-4 shrink-0 animate-spin text-muted" />
        )}
      </div>

      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label={`${label} suggestions`}
          className="absolute inset-x-0 top-full z-20 mt-1.5 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-lg shadow-ink/5"
        >
          {results.length === 0 && (
            <li className="px-3 py-2.5 text-sm text-muted">
              {geocode.isError ? 'Place search is unavailable right now.' : 'No places found.'}
            </li>
          )}
          {results.map((place, i) => (
            <li
              key={`${place.lat},${place.lon}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(place)}
              className={`flex cursor-pointer items-center gap-2.5 px-3 py-2 text-sm ${
                i === active ? 'bg-surface-2 text-ink' : 'text-ink-2'
              }`}
            >
              <MapPin aria-hidden className="size-4 shrink-0 text-muted" />
              <span className="truncate">{place.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
