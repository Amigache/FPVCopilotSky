import './TabBar.css'

const TabBar = ({ tabs, activeTab, onTabChange }) => {
  return (
    <div className="tab-bar">
      <div className="tab-bar-content">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default TabBar
