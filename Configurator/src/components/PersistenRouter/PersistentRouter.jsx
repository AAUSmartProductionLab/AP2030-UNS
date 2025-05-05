import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

/**
 * A component that keeps all routes mounted but only displays the active one
 * This is a completely new approach that bypasses React Router's remounting behavior
 */
export const PersistentRouter = ({ children }) => {
  // Create refs for each component to ensure they're only created once
  const componentsMap = useRef({});
  const initialRenderDone = useRef(false);
  const location = useLocation();
  
  // Create a stable mapping of routes to components, only on first render
  if (!initialRenderDone.current) {
    console.log('PersistentRouter: Creating component instances ONCE');
    
    // Process each Route child to extract the path and element
    React.Children.forEach(children, child => {
      if (!child?.props) return;
      
      const { path, element } = child.props;
      if (!path || !element) return;
      
      // Only create component instances once
      if (!componentsMap.current[path]) {
        // Store the actual JSX element, not just the component reference
        componentsMap.current[path] = {
          element,
          // Create an ID for this instance
          id: `route-${path.replace('/', '-')}`
        };
      }
    });
    
    initialRenderDone.current = true;
  }
  
  // Get current path
  const currentPath = location.pathname;
  
  // Wrap each element to handle its own visibility
  const wrappedComponents = useMemo(() => {
    return Object.entries(componentsMap.current).map(([path, { element, id }]) => {
      const isActive = 
        (path === '/' && (currentPath === '/' || currentPath === '')) || 
        (path === currentPath);
      
      return (
        <div 
          key={id}
          id={id}
          className={`persistent-route ${isActive ? 'active' : 'inactive'}`}
          style={{ 
            display: isActive ? 'block' : 'none',
            width: '100%',
            height: '100%'
          }}
          data-path={path}
        >
          {element}
        </div>
      );
    });
  }, [currentPath]); // Only re-create when the path changes
  
  return (
    <div className="persistent-router-container">
      {wrappedComponents}
    </div>
  );
};