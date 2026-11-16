package dde;

import org.bukkit.Material;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerDropItemEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerPickupItemEvent;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.PlayerInventory;
import org.bukkit.plugin.java.JavaPlugin;

/** Logs every item a player throws ("DD DROP ms MATERIAL amount") and fills a known test inventory. */
public class DropLog extends JavaPlugin implements Listener {
    static final Material[] ROW1 = {Material.STONE, Material.COBBLESTONE, Material.LOG, Material.WOOD, Material.SAND,
            Material.GRAVEL, Material.GLASS, Material.WOOL, Material.BRICK};
    static final Material[] ROW2 = {Material.COAL, Material.IRON_INGOT, Material.GOLD_INGOT, Material.DIAMOND,
            Material.REDSTONE, Material.STICK, Material.STRING, Material.FEATHER, Material.BONE};

    @Override
    public void onEnable() {
        getServer().getPluginManager().registerEvents(this, this);
    }

    void fill(Player p) {
        PlayerInventory inv = p.getInventory();
        inv.clear();
        inv.setArmorContents(new ItemStack[4]);
        inv.setHelmet(new ItemStack(Material.IRON_HELMET));
        for (int i = 0; i < 9; i++) {
            inv.setItem(9 + i, new ItemStack(ROW1[i], 16));
            inv.setItem(18 + i, new ItemStack(ROW2[i], 16));
        }
        inv.setItem(0, new ItemStack(Material.ARROW, 16));
        p.updateInventory();
        getLogger().info("DD READY " + p.getName());
    }

    @EventHandler
    public void onJoin(final PlayerJoinEvent e) {
        getServer().getScheduler().runTaskLater(this, new Runnable() {
            public void run() { fill(e.getPlayer()); }
        }, 40L);
    }

    @EventHandler
    public void onDrop(PlayerDropItemEvent e) {
        ItemStack s = e.getItemDrop().getItemStack();
        getLogger().info("DD DROP " + System.currentTimeMillis() + " " + s.getType() + " " + s.getAmount());
    }

    @EventHandler
    public void onPickup(PlayerPickupItemEvent e) {
        e.setCancelled(true);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {
        if (cmd.getName().equals("ddmark")) {
            getLogger().info("DD MARK " + System.currentTimeMillis() + " " + (args.length > 0 ? args[0] : "?"));
            return true;
        }
        if (cmd.getName().equals("ddfill") && sender instanceof Player) {
            fill((Player) sender);
            return true;
        }
        return false;
    }
}
