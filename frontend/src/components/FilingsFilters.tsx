export type SegmentFilter = 'All' | 'Mainboard' | 'SME'

export interface FilterState {
  query: string
  segment: SegmentFilter
  matchedOnly: boolean
}

interface FilingsFiltersProps {
  filters: FilterState
  onChange: (next: Partial<FilterState>) => void
}

export function FilingsFilters({ filters, onChange }: FilingsFiltersProps) {
  return (
    <div className="filters-bar">
      <label className="filters-field filters-field--grow">
        <span className="sr-only">Search</span>
        <input
          type="search"
          className="filters-input"
          placeholder="Search company / subject / scrip"
          value={filters.query}
          onChange={(e) => onChange({ query: e.target.value })}
        />
      </label>

      <label className="filters-field">
        <span className="filters-label">Segment</span>
        <select
          className="filters-select"
          value={filters.segment}
          onChange={(e) => onChange({ segment: e.target.value as SegmentFilter })}
        >
          <option value="All">All</option>
          <option value="Mainboard">Mainboard</option>
          <option value="SME">SME</option>
        </select>
      </label>

      <label className="filters-field filters-field--checkbox">
        <input
          type="checkbox"
          checked={filters.matchedOnly}
          onChange={(e) => onChange({ matchedOnly: e.target.checked })}
        />
        <span>Matched only</span>
      </label>
    </div>
  )
}
