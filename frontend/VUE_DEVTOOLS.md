# Vue DevTools Setup Guide

This guide explains how to set up and use Vue DevTools for debugging your Excludr frontend application.

## Quick Start (Recommended)

The easiest way to use Vue DevTools is with the browser extension:

### Chrome/Edge
Install from [Chrome Web Store](https://chrome.google.com/webstore/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd)

### Firefox
Install from [Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/vue-js-devtools/)

### Standalone App
For use outside browsers: [Vue DevTools Standalone](https://devtools.vuejs.org/guide/installation.html#standalone)

## Configuration

The project is already configured to work with Vue DevTools:

### 1. Vite Configuration (`vite.config.ts`)
- Vue compiler options are set to enable DevTools detection
- Development flags are properly configured
- Performance tracking is enabled in development mode

### 2. Main App Configuration (`src/main.ts`)
- Performance tracking is enabled in development mode via `app.config.performance = true`
- This allows DevTools to show component render times and performance metrics

## Using Vue DevTools

Once the browser extension is installed and your dev server is running:

1. Start the development server:
   ```bash
   npm run dev
   # or
   pnpm dev
   ```

2. Open your application in the browser (usually `http://localhost:5173`)

3. Open Browser DevTools (F12 or Ctrl+Shift+I / Cmd+Option+I)

4. Click on the "Vue" tab in DevTools

## Features Available

### Components Tab
- Inspect component hierarchy
- View component data, props, and computed properties
- Modify component state in real-time
- Track component lifecycle and performance

### Pinia (Store) Tab
You can inspect your Pinia stores:
- `auth` - Authentication state and user data
- `projects` - Project management state
- `articles` - Article data and filtering
- `criteria` - Search criteria state
- `screening` - Screening workflow state

### Router Tab
- View current route and params
- Navigate between routes
- Inspect route guards and navigation history

### Timeline Tab
- Track component lifecycle events
- Monitor store mutations/actions
- View performance metrics
- Debug async operations

### Performance Tab
- Component render times
- Update frequency
- Performance bottlenecks

## Troubleshooting

### DevTools Not Detecting App

1. **Check Extension is Enabled**
   - Ensure the Vue DevTools extension is enabled for your local development URL
   - Some extensions require explicit permission for localhost

2. **Verify Development Mode**
   - Make sure you're running the dev server (`npm run dev`)
   - Vue DevTools only works in development mode by default

3. **Clear Cache and Reload**
   - Sometimes a hard refresh (Ctrl+Shift+R / Cmd+Shift+R) is needed
   - Clear browser cache if issues persist

4. **Check Console for Errors**
   - Open browser console and look for Vue-related errors
   - Ensure no CSP (Content Security Policy) issues

### Extension Icon Not Green

If the extension icon is gray instead of green:
- The page doesn't have a Vue app detected
- Try refreshing the page
- Check that the app successfully mounted (look for errors in console)

### Performance Issues

If DevTools causes performance issues:
- Disable the Timeline tab when not in use
- Turn off performance tracking if not needed
- Use the browser extension instead of embedded devtools

## Advanced: Embedded DevTools (Optional)

If you need embedded devtools (not recommended for most cases):

1. Install the package:
   ```bash
   npm install --save-dev @vue/devtools
   # or
   pnpm add -D @vue/devtools
   ```

2. Import in `src/main.ts`:
   ```typescript
   if (import.meta.env.DEV) {
     import('@vue/devtools').then(devtools => {
       if (window) {
         devtools.default.connect('http://localhost', 8098)
       }
     })
   }
   ```

This is only needed for special cases (e.g., mobile debugging, Electron apps).

## Tips for Effective Debugging

1. **Use Component Inspector**
   - Click on components in the page to inspect them
   - Right-click in DevTools component tree for more options

2. **Time Travel Debugging**
   - Use the Timeline tab to replay events
   - Great for debugging complex user interactions

3. **Store Inspection**
   - Monitor Pinia store changes in real-time
   - Test store actions directly from DevTools

4. **Performance Profiling**
   - Use the Performance tab to identify slow components
   - Check render frequency and optimization opportunities

5. **Router Debugging**
   - Test navigation guards
   - Debug route parameter issues
   - View navigation history

## Resources

- [Official Vue DevTools Documentation](https://devtools.vuejs.org/)
- [Vue 3 Documentation](https://vuejs.org/)
- [Pinia DevTools Guide](https://pinia.vuejs.org/cookbook/testing.html#unit-testing-components)
