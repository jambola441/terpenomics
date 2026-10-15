// Adopt UIKit's scene-based life cycle on iOS.
//
// Apps built with the iOS 27 SDK refuse to launch without it ("UIScene life
// cycle is required for apps built with this SDK"). Expo SDK 57 ships the scene
// delegate, ExpoAppSceneDelegate, but its project template still starts React
// Native from the app delegate, so prebuild produces an app that doesn't launch.
// This wires the template up:
//
//   Info.plist        declares one window scene backed by EXExpoAppSceneDelegate
//                     (the Objective-C name of ExpoAppSceneDelegate).
//   AppDelegate.swift conforms to ExpoReactNativeFactoryProvider, which the
//                     scene delegate uses to find the React Native factory, and
//                     stops creating its own window, which the scene delegate
//                     now creates.
//
// Delete this plugin once Expo's template adopts scenes itself.
const { withAppDelegate, withInfoPlist } = require('expo/config-plugins')

const SCENE_DELEGATE = 'EXExpoAppSceneDelegate'

function withSceneManifest(config) {
  return withInfoPlist(config, cfg => {
    cfg.modResults.UIApplicationSceneManifest = {
      UIApplicationSupportsMultipleScenes: false,
      UISceneConfigurations: {
        UIWindowSceneSessionRoleApplication: [
          {
            UISceneConfigurationName: 'Default Configuration',
            UISceneDelegateClassName: SCENE_DELEGATE,
          },
        ],
      },
    }
    return cfg
  })
}

// The template's window setup in application(_:didFinishLaunchingWithOptions:).
const WINDOW_SETUP = /\n#if os\(iOS\) \|\| os\(tvOS\)\n\s*window = UIWindow\(frame: UIScreen\.main\.bounds\)\n\s*factory\.startReactNative\([\s\S]*?\)\n#endif\n/

function withSceneAppDelegate(config) {
  return withAppDelegate(config, cfg => {
    if (cfg.modResults.language !== 'swift') {
      throw new Error('withSceneLifecycle: expected a Swift AppDelegate')
    }
    let src = cfg.modResults.contents

    if (!src.includes('ExpoReactNativeFactoryProvider')) {
      const declaration = 'class AppDelegate: ExpoAppDelegate {'
      if (!src.includes(declaration)) {
        throw new Error(`withSceneLifecycle: AppDelegate no longer declares "${declaration}"; update this plugin`)
      }
      src = src.replace(declaration, 'class AppDelegate: ExpoAppDelegate, ExpoReactNativeFactoryProvider {')
    }

    if (WINDOW_SETUP.test(src)) {
      src = src.replace(
        WINDOW_SETUP,
        '\n    // The window and React Native are started by EXExpoAppSceneDelegate\n' +
          '    // (see plugins/withSceneLifecycle.js).\n',
      )
    } else if (src.includes('UIWindow(frame: UIScreen.main.bounds)')) {
      // Template changed shape: fail rather than ship an app that starts twice.
      throw new Error('withSceneLifecycle: could not remove the AppDelegate window setup; update this plugin')
    }

    cfg.modResults.contents = src
    return cfg
  })
}

module.exports = function withSceneLifecycle(config) {
  return withSceneAppDelegate(withSceneManifest(config))
}
