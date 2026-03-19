export default function Header({ config, onSettingsClick }) {
  return (
    <header className="site-header">
      <button className="settings-gear" onClick={onSettingsClick} title="Customise event">
        ⚙
      </button>

      <div className="header-divider">
        <span className="header-line" />
        <span>✦</span>
        <span className="header-line" />
      </div>

      <h1><em>{config.eventName}</em></h1>
      <p>{config.eventSubtitle}</p>
    </header>
  )
}
