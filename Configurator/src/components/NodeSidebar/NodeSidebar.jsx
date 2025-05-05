import React, { useState, useRef, useEffect } from 'react';
import { Task } from '../Task/Task';
import './NodeSidebar.css';

export const NodeSidebar = ({ categories }) => {
  // Start with all categories collapsed by default
  const [expandedCategories, setExpandedCategories] = useState({});
  const firstRender = useRef(true);
  
  // Initialize on first render only
  useEffect(() => {
    if (firstRender.current) {
      // For the first render, expand one category
      const initialState = {};
      if (categories.length > 0) {
        initialState[categories[0].id] = true;
      }
      setExpandedCategories(initialState);
      firstRender.current = false;
    }
  }, [categories]);

  const toggleCategory = (categoryId) => {
    setExpandedCategories(prev => ({
      ...prev,
      [categoryId]: !prev[categoryId]
    }));
  };

  return (
    <div className="node-sidebar">
      <div className="sidebar-header">
        <h2>Module Catalog</h2>
      </div>
      
      <div className="categories-container">
        {categories.map(category => (
          <div key={category.id} className="category">
            <div 
              className="category-header" 
              onClick={() => toggleCategory(category.id)}
            >
              <h3>{category.name}</h3>
              <span className={`arrow ${expandedCategories[category.id] ? 'expanded' : ''}`}>▶</span>
            </div>
            
            <div className={`category-nodes ${expandedCategories[category.id] ? 'expanded' : 'collapsed'}`}>
              <div className="category-nodes-inner">
                {category.nodes.map((node, index) => (
                  <div 
                    key={node.id} 
                    className="node-item"
                    style={{"--item-index": index}}
                  >
                    <Task 
                      id={node.id} 
                      title={node.title} 
                      color={node.color}
                      isTemplate
                      inSidebar={true}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};