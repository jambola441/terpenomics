// The app reuses the web portal's types and formatting helpers straight from
// ui/my-app/src (imported as `@web/...`, see tsconfig.json) rather than keeping
// a copy that drifts. Metro only sees files under the project root unless told
// otherwise, so that folder is added here.
const path = require('path')
const { getDefaultConfig } = require('expo/metro-config')

const config = getDefaultConfig(__dirname)
config.watchFolders = [path.resolve(__dirname, '../ui/my-app/src')]

module.exports = config
