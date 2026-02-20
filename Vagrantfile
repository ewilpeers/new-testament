Vagrant.configure("2") do |config|
  config.vm.box = "generic/alpine319"
  config.vm.hostname = "agent"

  config.vm.network "forwarded_port", guest: 3000, host: 3000  # Gitea web
  config.vm.network "forwarded_port", guest: 2222, host: 2222  # Gitea SSH

  config.vm.provider "virtualbox" do |vb|
    vb.memory = 4072
#have only 2 cores here..
    vb.cpus = 2
    vb.name = "calculus-agent"
#screen flick
    vb.customize ["modifyvm", :id, "--graphicscontroller", "vmsvga"]
    vb.customize ["modifyvm", :id, "--vram", "16"]
  end

  config.vm.synced_folder ".", "/vagrant", type: "virtualbox"
  config.vm.provision "ansible_local" do |ansible|
    ansible.playbook = "playbook.yml"
    ansible.install_mode = "pip"
  end
end
