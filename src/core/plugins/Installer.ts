import logger from "@logger";

export default class PluginInstaller {
	
	async install (plugin = { id: null, link: null}){
		setTimeout(() => {
			logger.info("Installing plugin...")
		}, 200)
		return {
			success: true,
			isInstalled: true,
		}
	}
	
	async uninstall (plugin = {id: null, link: null}){
		setTimeout(() => {
			logger.info("Uninstalling plugin...")
		}, 200)
		return {
			success: true,
			isUninstalled: true,
		}
	}
}

